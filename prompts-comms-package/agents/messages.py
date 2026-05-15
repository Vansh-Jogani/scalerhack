"""Typed inter-agent communication messages.

All handoffs between agents flow through these Pydantic models.
The orchestrator validates each message at the boundary — a malformed
report is rejected before it can corrupt downstream agent context.

Hierarchy:
  SurveillanceReport  — Agent 1 → Orchestrator → Agent 2
  SwarmFindings       — Agent 2 → Orchestrator → Agent 3 (via IncidentBriefing)
  IncidentBriefing    — Orchestrator → Agent 3
  WorldEvent          — World state / operator → Agent 3 trigger bus
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class SensorSummary(BaseModel):
    thermal_detected: bool
    survivor_probability: float = Field(ge=0.0, le=1.0)
    hazard_flags: list[str]
    wind_speed: float = Field(ge=0.0, description="m/s")
    visibility_m: float = Field(ge=0.0, description="meters")


class IncidentArea(BaseModel):
    center: dict  # {"lat": float, "lon": float}
    radius_m: float = Field(gt=0.0)


class ZoneFindings(BaseModel):
    thermal_signatures: int = Field(ge=0)
    structural_integrity: float = Field(ge=0.0, le=1.0)
    hazards_detected: list[str]
    survivor_count: int = Field(ge=0)


class ZoneAssessment(BaseModel):
    zone_id: str
    lat: float
    lon: float
    findings: ZoneFindings
    risk_level: Literal["low", "medium", "high", "critical"]
    actionable: bool


class SurvivorDetection(BaseModel):
    lat: float
    lon: float
    confidence: float = Field(ge=0.0, le=1.0)


class HazardMarker(BaseModel):
    lat: float
    lon: float
    type: str
    exclusion_radius_m: float = Field(gt=0.0)


# ---------------------------------------------------------------------------
# Deliverable 3a: Agent 1 → Orchestrator → Agent 2
# ---------------------------------------------------------------------------

class SurveillanceReport(BaseModel):
    """Produced by Agent 1. Passed to Orchestrator, then forwarded to Agent 2.

    Agent 2 receives this object. It does NOT receive Agent 1's tool-call
    history, messages array, or raw sensor readings.
    """
    incident_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    agent_version: str = "agent1_surveillance"
    prompt_version_hash: str

    classification: Literal[
        "fire", "structural_collapse", "flood", "industrial_hazard", "maritime_sar"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    area: IncidentArea
    sensor_summary: SensorSummary
    area_growth_detected: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Deliverable 3b: Agent 2 findings (feeds into IncidentBriefing)
# ---------------------------------------------------------------------------

class SwarmFindings(BaseModel):
    """Produced by Agent 2. Included in IncidentBriefing sent to Agent 3."""
    incident_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    agent_version: str = "agent2_specialist"
    prompt_version_hash: str

    zones_assessed: list[ZoneAssessment]
    survivor_detections: list[SurvivorDetection]
    hazard_map: list[HazardMarker]
    coverage_pct: float = Field(ge=0.0, le=100.0)
    notes: str = ""


# ---------------------------------------------------------------------------
# Deliverable 3c: Orchestrator → Agent 3
# ---------------------------------------------------------------------------

AgentTrigger = Literal[
    "agent_1_report_received",
    "agent_2_findings_updated",
    "world_event_fired",
    "operator_query",
    "heartbeat_check",
]


class IncidentBriefing(BaseModel):
    """The full context Agent 3 reasons over.

    Agent 3 receives this object. It does NOT receive Agent 1's or Agent 2's
    tool-call history, messages arrays, or intermediate reasoning.

    If previous_advisory is present, Agent 3 should update it rather than
    starting from scratch.
    """
    incident_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    trigger_type: AgentTrigger

    surveillance_report: SurveillanceReport
    swarm_findings: Optional[SwarmFindings] = None
    previous_advisory: Optional[dict] = None


# ---------------------------------------------------------------------------
# Deliverable 3d: World events → Agent 3 trigger bus
# ---------------------------------------------------------------------------

WorldTrigger = Literal[
    "fire_grew",
    "aftershock",
    "new_survivor_detected",
    "operator_query",
    "heartbeat_check",
]


class WorldEvent(BaseModel):
    """Emitted by world state or operator API. Published to the event bus."""
    incident_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    trigger_type: WorldTrigger
    payload: dict = Field(default_factory=dict)
    source: str = Field(description="Component that fired this event")
