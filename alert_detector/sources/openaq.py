"""OpenAQ v3 API poller for Hyderabad PM2.5 readings.

OpenAQ migrated to v3 in 2024. v2 is deprecated.
Base URL: https://api.openaq.org/v3
Auth: X-API-Key header (free key at explore.openaq.org/register)

Strategy:
  1. On first poll, discover sensor location IDs within Hyderabad bbox
     via GET /v3/locations?bbox=78.20,17.20,78.65,17.65&parameters_id=2
     (parameters_id=2 is PM2.5)
  2. Cache those location IDs.
  3. On each poll, fetch latest readings for each location via
     GET /v3/locations/{id}/latest
  4. Filter for PM2.5 > 150 µg/m³ within last 10 minutes.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import structlog

from alert_detector.signals import AirQualitySignal

logger = structlog.get_logger()

OPENAQ_BASE = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2          # OpenAQ canonical ID for PM2.5
PM25_HAZARDOUS_THRESHOLD = 150  # µg/m³
STALE_READING_MINUTES = 10


class OpenAQPoller:
    """Polls OpenAQ v3 for hazardous PM2.5 readings in Hyderabad."""

    def __init__(self, api_key: str, bbox: dict):
        """
        Args:
            api_key: OpenAQ API key (X-API-Key header).
            bbox: dict with lat_min, lat_max, lon_min, lon_max.
        """
        self._api_key = api_key
        self._bbox = bbox
        self._location_ids: list[int] = []
        self._location_names: dict[int, str] = {}
        self._location_coords: dict[int, tuple[float, float]] = {}
        self._locations_discovered = False

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self._api_key and self._api_key != "YOUR_OPENAQ_API_KEY":
            h["X-API-Key"] = self._api_key
        return h

    async def _discover_locations(self, client: httpx.AsyncClient) -> None:
        """Query locations within Hyderabad bbox that have PM2.5 sensors."""
        bbox_str = (
            f"{self._bbox['lon_min']},{self._bbox['lat_min']},"
            f"{self._bbox['lon_max']},{self._bbox['lat_max']}"
        )
        try:
            resp = await client.get(
                f"{OPENAQ_BASE}/locations",
                params={
                    "bbox": bbox_str,
                    "parameters_id": PM25_PARAMETER_ID,
                    "limit": 100,
                },
                headers=self._headers(),
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("openaq_discover_error", error=str(e))
            return

        results = data.get("results", [])
        for loc in results:
            loc_id = loc.get("id")
            name = loc.get("name", f"location-{loc_id}")
            coords = loc.get("coordinates", {})
            lat = coords.get("latitude")
            lon = coords.get("longitude")
            if loc_id and lat is not None and lon is not None:
                self._location_ids.append(loc_id)
                self._location_names[loc_id] = name
                self._location_coords[loc_id] = (lat, lon)

        self._locations_discovered = True
        logger.info(
            "openaq_locations_discovered",
            count=len(self._location_ids),
            ids=self._location_ids,
        )

    def _has_valid_key(self) -> bool:
        return bool(self._api_key) and self._api_key not in ("", "YOUR_OPENAQ_API_KEY")

    async def poll(self) -> list[AirQualitySignal]:
        """Fetch latest PM2.5 readings, return signals above hazardous threshold."""
        if not self._has_valid_key():
            logger.info("openaq_skipped", reason="no_api_key_configured")
            return []

        signals: list[AirQualitySignal] = []
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=STALE_READING_MINUTES)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                if not self._locations_discovered:
                    await self._discover_locations(client)

                if not self._location_ids:
                    logger.warning("openaq_no_locations_found")
                    return []

                for loc_id in self._location_ids:
                    try:
                        resp = await client.get(
                            f"{OPENAQ_BASE}/locations/{loc_id}/latest",
                            headers=self._headers(),
                            timeout=10.0,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except httpx.HTTPError as e:
                        logger.warning("openaq_location_poll_error",
                                       location_id=loc_id, error=str(e))
                        continue

                    for result in data.get("results", []):
                        # Each result has sensors array
                        for sensor in result.get("sensors", []):
                            param = sensor.get("parameter", {})
                            if param.get("id") != PM25_PARAMETER_ID:
                                continue

                            latest = sensor.get("latest", {})
                            value = latest.get("value")
                            datetime_str = latest.get("datetime", {})
                            if isinstance(datetime_str, dict):
                                datetime_str = datetime_str.get("utc", "")

                            if value is None or value < PM25_HAZARDOUS_THRESHOLD:
                                continue

                            # Parse timestamp
                            try:
                                ts = datetime.fromisoformat(
                                    datetime_str.replace("Z", "+00:00")
                                )
                            except (ValueError, AttributeError):
                                ts = datetime.now(tz=timezone.utc)

                            if ts < cutoff:
                                logger.debug("openaq_stale_reading",
                                             location_id=loc_id, ts=ts)
                                continue

                            lat, lon = self._location_coords.get(loc_id, (17.385, 78.486))
                            signal = AirQualitySignal(
                                lat=lat,
                                lon=lon,
                                pm25=value,
                                location_id=loc_id,
                                location_name=self._location_names.get(loc_id, "unknown"),
                                timestamp=ts,
                            )
                            signals.append(signal)
                            logger.info(
                                "openaq_signal_detected",
                                location_id=loc_id,
                                pm25=value,
                                lat=lat, lon=lon,
                            )

        except Exception as e:
            logger.error("openaq_poll_error", error=str(e))

        return signals
