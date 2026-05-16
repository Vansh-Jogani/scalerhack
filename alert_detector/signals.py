"""Signal dataclasses for the ARIA Alert Detection Layer.

Each signal type carries its source-specific fields plus a confidence
contribution value used by the fusion engine in detector.py.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SeismicSignal:
    """From USGS GeoJSON feed. HIGH confidence contribution."""
    lat: float
    lon: float
    magnitude: float
    place: str
    event_id: str
    timestamp: datetime
    confidence_contribution: float = 65.0
    source: str = "usgs"


@dataclass
class AirQualitySignal:
    """From OpenAQ v3 API. MEDIUM confidence contribution."""
    lat: float
    lon: float
    pm25: float                  # µg/m³
    location_id: int
    location_name: str
    timestamp: datetime
    confidence_contribution: float = 30.0
    source: str = "openaq"


@dataclass
class EmergencySignal:
    """From POST /sim/emergency_signal (112 call spike). HIGH confidence."""
    lat: float
    lon: float
    call_count: int
    timestamp: datetime
    confidence_contribution: float = 55.0
    source: str = "emergency_112"


@dataclass
class SocialSignal:
    """From POST /sim/social_signal (social media spike). LOW confidence."""
    lat: float
    lon: float
    keyword: str
    count: int
    timestamp: datetime
    confidence_contribution: float = 20.0
    source: str = "social"


@dataclass
class ManualTrigger:
    """From POST /sim/manual_trigger (commander override). 100% confidence."""
    lat: float
    lon: float
    disaster_type: str
    severity: str
    timestamp: datetime
    confidence_contribution: float = 100.0
    source: str = "manual"
