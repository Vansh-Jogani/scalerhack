"""Typed handoff payloads between agents and orchestrator."""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class SurveillanceReport(BaseModel):
    incident_id: str
    timestamp: str = ""
    agent_version: str = "1.0"
    prompt_version_hash: str = ""
    classification: str
    confidence: float
    area: dict
    sensor_summary: dict
    notes: str = ""

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be 0–1, got {v}")
        return v

    @classmethod
    def from_tool_call(cls, kwargs: dict, prompt_version_hash: str = "") -> "SurveillanceReport":
        return cls(
            **kwargs,
            prompt_version_hash=prompt_version_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class SwarmFindings(BaseModel):
    incident_id: str
    timestamp: str = ""
    agent_version: str = "2.0"
    prompt_version_hash: str = ""
    zones_assessed: list[dict] = []
    survivor_detections: list[dict] = []
    hazard_map: list[dict] = []
    coverage_pct: float = 0.0
    notes: str = ""

    @classmethod
    def from_tool_call(cls, kwargs: dict, prompt_version_hash: str = "") -> "SwarmFindings":
        return cls(
            **kwargs,
            prompt_version_hash=prompt_version_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class IncidentBriefing(BaseModel):
    incident_id: str
    timestamp: str = ""
    surveillance_report: Optional[Any] = None
    swarm_findings: Optional[Any] = None
    previous_advisory: Optional[dict] = None

    @classmethod
    def from_dicts(
        cls,
        incident_id: str,
        a1_data: dict,
        a2_data: dict,
        previous_advisory: Optional[dict] = None,
    ) -> "IncidentBriefing":
        sr: Any = None
        if a1_data:
            try:
                sr = SurveillanceReport(**a1_data)
            except Exception:
                sr = a1_data

        sf: Any = None
        if a2_data:
            try:
                sf = SwarmFindings(**a2_data)
            except Exception:
                sf = a2_data

        return cls(
            incident_id=incident_id,
            surveillance_report=sr,
            swarm_findings=sf,
            previous_advisory=previous_advisory,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def to_context_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "timestamp": self.timestamp,
            "surveillance_report": (
                self.surveillance_report.model_dump()
                if hasattr(self.surveillance_report, "model_dump")
                else self.surveillance_report
            ),
            "swarm_findings": (
                self.swarm_findings.model_dump()
                if hasattr(self.swarm_findings, "model_dump")
                else self.swarm_findings
            ),
            "previous_advisory": self.previous_advisory,
        }


class WorldEvent(BaseModel):
    incident_id: str
    timestamp: str = ""
    event_type: str
    details: dict = {}
