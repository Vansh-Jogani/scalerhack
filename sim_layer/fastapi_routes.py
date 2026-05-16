"""FastAPI routes for simulated signal injection and alert detector status.

Endpoints:
  POST /sim/emergency_signal  — simulate 112 call spike
  POST /sim/social_signal     — simulate social media spike
  POST /sim/manual_trigger    — commander override (bypasses confidence gate)
  GET  /alert_detector/status — current detector state
"""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

# Detector instance is injected at startup via set_detector()
_detector = None


def set_detector(detector) -> None:
    """Called from main.py lifespan after AlertDetector is created."""
    global _detector
    _detector = detector


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class EmergencySignalRequest(BaseModel):
    lat: float
    lon: float
    call_count: int
    timestamp: str | None = None  # ISO8601; defaults to now if omitted


class SocialSignalRequest(BaseModel):
    lat: float
    lon: float
    keyword: str
    count: int
    timestamp: str | None = None


class ManualTriggerRequest(BaseModel):
    lat: float
    lon: float
    disaster_type: str = "unknown"
    severity: str = "medium"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/sim/emergency_signal")
async def emergency_signal(req: EmergencySignalRequest):
    """Inject a simulated 112 emergency call spike."""
    if _detector is None:
        raise HTTPException(status_code=503, detail="Alert detector not initialised")

    ts = _parse_timestamp(req.timestamp)
    logger.info("sim_emergency_signal_received",
                lat=req.lat, lon=req.lon, call_count=req.call_count)

    await _detector.on_emergency_signal(
        lat=req.lat,
        lon=req.lon,
        call_count=req.call_count,
        timestamp=ts,
    )
    return {"status": "ok", "call_count": req.call_count}


@router.post("/sim/social_signal")
async def social_signal(req: SocialSignalRequest):
    """Inject a simulated social media spike."""
    if _detector is None:
        raise HTTPException(status_code=503, detail="Alert detector not initialised")

    ts = _parse_timestamp(req.timestamp)
    logger.info("sim_social_signal_received",
                lat=req.lat, lon=req.lon, keyword=req.keyword, count=req.count)

    await _detector.on_social_signal(
        lat=req.lat,
        lon=req.lon,
        keyword=req.keyword,
        count=req.count,
        timestamp=ts,
    )
    return {"status": "ok", "count": req.count}


@router.post("/sim/manual_trigger")
async def manual_trigger(req: ManualTriggerRequest):
    """Commander override — bypasses confidence gate, fires go signal immediately."""
    if _detector is None:
        raise HTTPException(status_code=503, detail="Alert detector not initialised")

    logger.info("sim_manual_trigger_received",
                lat=req.lat, lon=req.lon,
                disaster_type=req.disaster_type, severity=req.severity)

    await _detector.on_manual_trigger(
        lat=req.lat,
        lon=req.lon,
        disaster_type=req.disaster_type,
        severity=req.severity,
    )
    return {
        "status": "ok",
        "disaster_type": req.disaster_type,
        "severity": req.severity,
    }


@router.get("/alert_detector/status")
async def alert_detector_status():
    """Return current alert detector state."""
    if _detector is None:
        return {
            "active_signals": [],
            "current_confidence": 0.0,
            "last_poll_times": {"usgs": None, "openaq": None},
            "threshold": 70,
            "go_signals_fired_today": 0,
        }
    return _detector.get_status()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str: str | None) -> datetime:
    if not ts_str:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=timezone.utc)
