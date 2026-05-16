"""USGS Earthquake GeoJSON feed poller.

Fetches: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_hour.geojson
Schema confirmed from live feed:
  features[].geometry.coordinates → [lon, lat, depth_km]
  features[].properties.mag       → float
  features[].properties.place     → str
  features[].properties.time      → int (Unix ms)
  features[].id                   → str

Poll interval: 60s minimum (feed is cached 60s server-side).
No auth required.
"""

from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from alert_detector.signals import SeismicSignal

logger = structlog.get_logger()

USGS_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_hour.geojson"
)

# India bounding box — broad filter before Hyderabad bbox
INDIA_LAT_MIN = 8.0
INDIA_LAT_MAX = 37.0
INDIA_LON_MIN = 68.0
INDIA_LON_MAX = 98.0
MIN_MAGNITUDE = 4.0


class USGSPoller:
    """Polls the USGS significant earthquakes feed and returns SeismicSignals."""

    def __init__(self):
        self._seen_ids: set[str] = set()

    async def poll(self) -> list[SeismicSignal]:
        """Fetch feed, filter by India bbox + magnitude, return new signals only."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(USGS_URL)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("usgs_poll_error", error=str(e))
            return []
        except Exception as e:
            logger.error("usgs_parse_error", error=str(e))
            return []

        signals: list[SeismicSignal] = []
        features = data.get("features", [])

        for feature in features:
            event_id = feature.get("id", "")
            if event_id in self._seen_ids:
                continue

            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [])

            if len(coords) < 2:
                continue

            lon, lat = coords[0], coords[1]
            mag = props.get("mag")
            place = props.get("place", "unknown")
            time_ms = props.get("time", 0)

            if mag is None or mag < MIN_MAGNITUDE:
                continue

            # Filter to India bounding box
            if not (INDIA_LAT_MIN <= lat <= INDIA_LAT_MAX and
                    INDIA_LON_MIN <= lon <= INDIA_LON_MAX):
                logger.info(
                    "usgs_signal_outside_india",
                    lat=lat, lon=lon, mag=mag, place=place,
                )
                continue

            ts = datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc)
            signal = SeismicSignal(
                lat=lat,
                lon=lon,
                magnitude=mag,
                place=place,
                event_id=event_id,
                timestamp=ts,
            )
            signals.append(signal)
            self._seen_ids.add(event_id)
            logger.info(
                "usgs_signal_detected",
                event_id=event_id, lat=lat, lon=lon, mag=mag, place=place,
            )

        return signals
