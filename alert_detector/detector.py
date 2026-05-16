"""ARIA Alert Detector — autonomous disaster signal fusion engine.

Runs as a background asyncio task. Monitors USGS + OpenAQ continuously.
Accepts push signals from FastAPI sim endpoints.
Fuses signals into a confidence score and fires go signal to orchestrator
when confidence >= threshold.

Signal TTL: 5 minutes (signals older than this are dropped from the window).
"""

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

from alert_detector.signals import (
    SeismicSignal,
    AirQualitySignal,
    EmergencySignal,
    SocialSignal,
    ManualTrigger,
)
from alert_detector.sources.usgs import USGSPoller
from alert_detector.sources.openaq import OpenAQPoller

logger = structlog.get_logger()

SIGNAL_TTL_MINUTES = 5

# Type alias for any signal
AnySignal = SeismicSignal | AirQualitySignal | EmergencySignal | SocialSignal | ManualTrigger


class AlertDetector:
    """Continuous background detector. Fuses signals, fires go signal autonomously."""

    def __init__(self, config: dict, orchestrator):
        """
        Args:
            config: Full config dict (reads alert_detector sub-key).
            orchestrator: ARIAOrchestrator instance.
        """
        self._orchestrator = orchestrator
        cfg = config.get("alert_detector", {})

        self._threshold: float = float(cfg.get("confidence_threshold", 70))
        self._poll_interval: int = int(cfg.get("poll_interval_seconds", 60))
        self._bbox: dict = cfg.get("hyderabad_bbox", {
            "lat_min": 17.20, "lat_max": 17.65,
            "lon_min": 78.20, "lon_max": 78.65,
        })
        openaq_key: str = cfg.get("openaq_api_key", "")

        self._usgs = USGSPoller()
        self._openaq = OpenAQPoller(api_key=openaq_key, bbox=self._bbox)

        # Rolling signal window — deque of (received_at, signal)
        self._signal_window: deque[tuple[datetime, AnySignal]] = deque()

        # Stats
        self._go_signals_fired_today: int = 0
        self._last_poll_usgs: datetime | None = None
        self._last_poll_openaq: datetime | None = None
        self._current_confidence: float = 0.0

        # Cooldown: don't fire again within 5 minutes of last fire
        self._last_fire_time: datetime | None = None
        self._fire_cooldown_seconds: int = 300

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch polling loops as concurrent background tasks."""
        logger.info("alert_detector_started",
                    threshold=self._threshold,
                    poll_interval=self._poll_interval)
        await asyncio.gather(
            self._usgs_loop(),
            self._openaq_loop(),
        )

    # ------------------------------------------------------------------
    # Polling loops
    # ------------------------------------------------------------------

    async def _usgs_loop(self) -> None:
        """Poll USGS every poll_interval seconds."""
        while True:
            try:
                signals = await self._usgs.poll()
                self._last_poll_usgs = datetime.now(tz=timezone.utc)
                for sig in signals:
                    await self._ingest(sig)
            except Exception as e:
                logger.error("usgs_loop_error", error=str(e))
            await asyncio.sleep(self._poll_interval)

    async def _openaq_loop(self) -> None:
        """Poll OpenAQ every poll_interval seconds."""
        while True:
            try:
                signals = await self._openaq.poll()
                self._last_poll_openaq = datetime.now(tz=timezone.utc)
                for sig in signals:
                    await self._ingest(sig)
            except Exception as e:
                logger.error("openaq_loop_error", error=str(e))
            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Push signal handlers (called from FastAPI routes)
    # ------------------------------------------------------------------

    async def on_emergency_signal(self, lat: float, lon: float,
                                   call_count: int, timestamp: datetime) -> None:
        """Handle 112 emergency call spike from /sim/emergency_signal."""
        if call_count <= 50:
            logger.info("emergency_signal_below_threshold", call_count=call_count)
            return
        sig = EmergencySignal(lat=lat, lon=lon, call_count=call_count, timestamp=timestamp)
        await self._ingest(sig)

    async def on_social_signal(self, lat: float, lon: float,
                                keyword: str, count: int, timestamp: datetime) -> None:
        """Handle social media spike from /sim/social_signal."""
        if count <= 200:
            logger.info("social_signal_below_threshold", count=count)
            return
        sig = SocialSignal(lat=lat, lon=lon, keyword=keyword, count=count, timestamp=timestamp)
        await self._ingest(sig)

    async def on_manual_trigger(self, lat: float, lon: float,
                                 disaster_type: str, severity: str,
                                 zone_radius_m: float | None = None,
                                 zone_polygon: list | None = None) -> None:
        """Handle commander override from /sim/manual_trigger or admin panel.

        Bypasses confidence gate entirely — fires go signal immediately.
        Accepts optional zone geometry so the orchestrator gets full area context.
        """
        sig = ManualTrigger(
            lat=lat, lon=lon,
            disaster_type=disaster_type,
            severity=severity,
            timestamp=datetime.now(tz=timezone.utc),
        )
        logger.info("manual_trigger_received",
                    lat=lat, lon=lon, disaster_type=disaster_type, severity=severity)
        await self._fire_go_signal(
            [sig],
            confidence=100.0,
            estimated_type=disaster_type,
            zone_radius_m=zone_radius_m,
            zone_polygon=zone_polygon,
        )

    # ------------------------------------------------------------------
    # Core ingestion + fusion
    # ------------------------------------------------------------------

    async def _ingest(self, signal: AnySignal) -> None:
        """Add signal to window, check bbox, run fusion."""
        # Bbox check
        if not self._in_hyderabad_bbox(signal.lat, signal.lon):
            logger.info(
                "signal_outside_hyderabad_bbox",
                source=signal.source, lat=signal.lat, lon=signal.lon,
            )
            return

        now = datetime.now(tz=timezone.utc)
        self._signal_window.append((now, signal))
        logger.info(
            "signal_ingested",
            source=signal.source,
            lat=signal.lat, lon=signal.lon,
            contribution=signal.confidence_contribution,
        )

        await self._evaluate()

    async def _evaluate(self) -> None:
        """Prune stale signals, compute confidence, fire if threshold met."""
        self._prune_stale()

        active = [sig for _, sig in self._signal_window]
        if not active:
            self._current_confidence = 0.0
            return

        confidence, estimated_type = self._fuse(active)
        self._current_confidence = confidence

        logger.info(
            "confidence_calculated",
            confidence=confidence,
            threshold=self._threshold,
            signal_count=len(active),
            estimated_type=estimated_type,
        )

        if confidence >= self._threshold:
            # Cooldown check
            now = datetime.now(tz=timezone.utc)
            if (self._last_fire_time and
                    (now - self._last_fire_time).total_seconds() < self._fire_cooldown_seconds):
                logger.info("go_signal_suppressed_cooldown",
                            seconds_since_last=int((now - self._last_fire_time).total_seconds()))
                return

            await self._fire_go_signal(active, confidence, estimated_type)

    def _fuse(self, signals: list[AnySignal]) -> tuple[float, str]:
        """Apply confidence fusion rules. Returns (confidence_pct, estimated_type)."""
        has_seismic = any(isinstance(s, SeismicSignal) for s in signals)
        has_air = any(isinstance(s, AirQualitySignal) for s in signals)
        has_emergency = any(isinstance(s, EmergencySignal) for s in signals)
        has_social = any(isinstance(s, SocialSignal) for s in signals)

        signal_count = sum([has_seismic, has_air, has_emergency, has_social])

        # Base confidence from combination rules
        if has_seismic and has_emergency:
            confidence = 85.0
        elif has_seismic and has_air:
            confidence = 75.0
        elif signal_count >= 3:
            confidence = 90.0
        else:
            # Sum individual contributions
            confidence = 0.0
            if has_seismic:
                confidence += 65.0
            if has_air:
                confidence += 30.0
            if has_emergency:
                confidence += 55.0
            if has_social:
                confidence += 20.0
            # Cap at 95 for non-manual
            confidence = min(confidence, 95.0)

        # Social bonus: any single signal + social
        if has_social and signal_count == 2:
            confidence += 10.0

        confidence = min(confidence, 100.0)

        # Estimate disaster type
        if has_seismic and not has_air:
            estimated_type = "structural_collapse"
        elif has_air and not has_seismic:
            estimated_type = "fire"
        elif has_seismic and has_air:
            estimated_type = "structural_collapse"  # seismic dominant
        elif has_emergency:
            estimated_type = "unknown"
        else:
            estimated_type = "unknown"

        return confidence, estimated_type

    async def _fire_go_signal(self, signals: list[AnySignal],
                               confidence: float, estimated_type: str,
                               zone_radius_m: float | None = None,
                               zone_polygon: list | None = None) -> None:
        """Build marker and call orchestrator.on_go_signal()."""
        # Compute centroid of all signal locations
        lats = [s.lat for s in signals]
        lons = [s.lon for s in signals]
        lat = sum(lats) / len(lats)
        lon = sum(lons) / len(lons)

        source_names = list({s.source for s in signals})

        marker = {
            "id": f"ALERT-{uuid.uuid4().hex[:8].upper()}",
            "lat": lat,
            "lon": lon,
            "type": estimated_type,
            "radius_m": zone_radius_m or 500.0,
            "severity": self._severity_from_confidence(confidence),
            "confirmed": False,
        }

        logger.info(
            "go_signal_fired",
            marker_id=marker["id"],
            lat=lat, lon=lon,
            confidence=confidence,
            estimated_type=estimated_type,
            signal_sources=source_names,
        )

        self._last_fire_time = datetime.now(tz=timezone.utc)
        self._go_signals_fired_today += 1

        # Clear signal window after firing to avoid re-triggering
        self._signal_window.clear()

        try:
            await self._orchestrator.on_go_signal(
                marker=marker,
                confidence=confidence,
                signal_sources=source_names,
                zone_polygon=zone_polygon,
            )
        except Exception as e:
            logger.error("go_signal_dispatch_error", error=str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _in_hyderabad_bbox(self, lat: float, lon: float) -> bool:
        return (
            self._bbox["lat_min"] <= lat <= self._bbox["lat_max"] and
            self._bbox["lon_min"] <= lon <= self._bbox["lon_max"]
        )

    def _prune_stale(self) -> None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=SIGNAL_TTL_MINUTES)
        while self._signal_window and self._signal_window[0][0] < cutoff:
            self._signal_window.popleft()

    @staticmethod
    def _severity_from_confidence(confidence: float) -> str:
        if confidence >= 90:
            return "critical"
        if confidence >= 75:
            return "high"
        if confidence >= 55:
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # Status endpoint data
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return status dict for GET /alert_detector/status."""
        self._prune_stale()
        active = [
            {
                "source": sig.source,
                "lat": sig.lat,
                "lon": sig.lon,
                "contribution": sig.confidence_contribution,
                "received_at": received_at.isoformat(),
            }
            for received_at, sig in self._signal_window
        ]
        return {
            "active_signals": active,
            "current_confidence": self._current_confidence,
            "last_poll_times": {
                "usgs": self._last_poll_usgs.isoformat() if self._last_poll_usgs else None,
                "openaq": self._last_poll_openaq.isoformat() if self._last_poll_openaq else None,
            },
            "threshold": self._threshold,
            "go_signals_fired_today": self._go_signals_fired_today,
        }
