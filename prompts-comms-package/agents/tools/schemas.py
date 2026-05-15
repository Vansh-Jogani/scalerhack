"""Typed tool schemas for all ARIA agents.

Each class is a Pydantic model that:
  - validates incoming tool call inputs before they reach the simulation
  - emits the exact tool dict the Claude API expects via to_claude_tool_dict()

Usage:
    tool_dict = FlyToInput.to_claude_tool_dict()          # pass to Claude API
    obj, err = FlyToInput.validate_call(block.input)      # validate at boundary
"""

from typing import ClassVar, Literal
from pydantic import BaseModel, Field, ValidationError


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class ToolInput(BaseModel):
    TOOL_NAME: ClassVar[str] = ""
    TOOL_DESCRIPTION: ClassVar[str] = ""

    @classmethod
    def to_claude_tool_dict(cls) -> dict:
        schema = cls.model_json_schema()
        _strip_titles(schema)
        return {
            "name": cls.TOOL_NAME,
            "description": cls.TOOL_DESCRIPTION,
            "input_schema": schema,
        }

    @classmethod
    def validate_call(cls, kwargs: dict) -> tuple["ToolInput | None", "str | None"]:
        try:
            return cls.model_validate(kwargs), None
        except ValidationError as e:
            return None, e.json()


def _strip_titles(schema: dict) -> None:
    schema.pop("title", None)
    for v in schema.values():
        if isinstance(v, dict):
            _strip_titles(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _strip_titles(item)


# ---------------------------------------------------------------------------
# Agent 1 tools
# ---------------------------------------------------------------------------

class FlyToInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "fly_to"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Command a drone to fly to specified coordinates at the given altitude. "
        "The drone begins moving at cruise speed. Returns when the command is accepted, "
        "not when the drone arrives."
    )
    drone_id: str = Field(description="ID of the drone to command")
    lat: float = Field(description="Target latitude (decimal degrees)")
    lon: float = Field(description="Target longitude (decimal degrees)")
    alt: float = Field(description="Target altitude in meters AGL", ge=60.0)


class LoiterOverInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "loiter_over"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Command a drone to enter a circular loiter pattern over a point. "
        "The drone will orbit at the given radius and altitude for duration_s seconds, "
        "then hold position. Use after classification is confirmed."
    )
    drone_id: str = Field(description="ID of the drone to command")
    lat: float = Field(description="Center of loiter circle (decimal degrees)")
    lon: float = Field(description="Center of loiter circle (decimal degrees)")
    radius_m: float = Field(description="Loiter radius in meters", ge=20.0)
    duration_s: float = Field(description="Duration in seconds (0 = hold indefinitely)", ge=0.0)


class GetSensorReadingInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "get_sensor_reading"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Read all sensors at the drone's current position. "
        "Returns sensor data if the drone is over an active incident area, "
        "or status='no_data' if outside any incident zone."
    )
    drone_id: str = Field(description="ID of the drone to read sensors from")


class _SensorSummaryInput(BaseModel):
    thermal_detected: bool
    survivor_probability: float = Field(ge=0.0, le=1.0)
    hazard_flags: list[str]
    wind_speed: float = Field(ge=0.0, description="m/s")
    visibility_m: float = Field(ge=0.0, description="meters")


class _AreaCenterInput(BaseModel):
    lat: float
    lon: float


class _AreaInput(BaseModel):
    center: _AreaCenterInput
    radius_m: float = Field(gt=0.0)


class ReportClassificationInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "report_classification"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Report the incident classification to the orchestrator after completing "
        "a full orbit with consistent sensor data. Call exactly once per mission."
    )
    incident_id: str = Field(description="Incident ID in format INC-{unix_timestamp}")
    classification: Literal[
        "fire", "structural_collapse", "flood", "industrial_hazard", "maritime_sar"
    ]
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    area: _AreaInput
    sensor_summary: _SensorSummaryInput
    area_growth_detected: bool = Field(
        default=False,
        description="True if incident area appears larger than the initial marker suggested",
    )
    notes: str = Field(default="", description="Additional observations")


class RequestDetailedPassInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "request_detailed_pass"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Command the drone to descend to 60 m AGL for a close-range sensor pass "
        "over the specified coordinates. Use only when the standard-altitude reading "
        "is ambiguous and a lower pass is operationally safe."
    )
    drone_id: str = Field(description="ID of the drone")
    lat: float = Field(description="Target latitude for the detailed pass")
    lon: float = Field(description="Target longitude for the detailed pass")


# ---------------------------------------------------------------------------
# Agent 2 tools
# ---------------------------------------------------------------------------

class SwarmPosition(BaseModel):
    drone_id: str = Field(description="ID of the swarm drone to position")
    lat: float = Field(description="Target latitude (decimal degrees)")
    lon: float = Field(description="Target longitude (decimal degrees)")
    alt: float = Field(description="Target altitude in meters AGL", ge=10.0)


class DeploySwarmInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "deploy_swarm"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Position all swarm drones simultaneously by specifying a target position "
        "for each drone. Can be called multiple times to reposition the swarm. "
        "Each position must respect the operational altitude and constraint for this swarm type."
    )
    positions: list[SwarmPosition] = Field(
        description="Target position for each swarm drone", min_length=1
    )


class _ZoneFindingsInput(BaseModel):
    thermal_signatures: int = Field(ge=0, description="Count of thermal detections")
    structural_integrity: float = Field(ge=0.0, le=1.0, description="0.0=collapsed, 1.0=intact")
    hazards_detected: list[str] = Field(description="Named hazards found in zone")
    survivor_count: int = Field(ge=0, description="Confirmed or probable survivors")


class UpdateZoneClassificationInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "update_zone_classification"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Write a zone assessment to the world state after surveying a zone. "
        "Call once per zone after get_sensor_reading returns data for that zone."
    )
    zone_id: str = Field(description="Zone ID in format ZONE-{lat:.4f}-{lon:.4f}")
    lat: float
    lon: float
    findings: _ZoneFindingsInput
    risk_level: Literal["low", "medium", "high", "critical"]
    actionable: bool = Field(
        description="True only if risk_level is high/critical AND sensor-confirmed, not inferred"
    )


class MarkSurvivorInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "mark_survivor"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Mark a survivor detection on the world state immediately upon detection. "
        "Do not wait for full coverage — call this as soon as a survivor is detected."
    )
    lat: float = Field(description="Survivor latitude")
    lon: float = Field(description="Survivor longitude")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence")
    drone_id: str = Field(description="ID of the detecting drone")


class MarkHazardInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "mark_hazard"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Mark a hazard and its exclusion zone on the world state. "
        "Call immediately upon hazard detection."
    )
    lat: float = Field(description="Hazard source latitude")
    lon: float = Field(description="Hazard source longitude")
    type: str = Field(description="Hazard type (e.g. 'chemical_leak', 'structural_collapse_risk')")
    exclusion_radius_m: float = Field(gt=0.0, description="Radius humans must not enter")
    drone_id: str = Field(description="ID of the detecting drone")


class _SurvivorDetectionInput(BaseModel):
    lat: float
    lon: float
    confidence: float = Field(ge=0.0, le=1.0)


class _HazardMapEntryInput(BaseModel):
    lat: float
    lon: float
    type: str
    exclusion_radius_m: float = Field(gt=0.0)


class _ZoneAssessmentInput(BaseModel):
    zone_id: str
    lat: float
    lon: float
    findings: _ZoneFindingsInput
    risk_level: Literal["low", "medium", "high", "critical"]
    actionable: bool


class ReportSwarmFindingsInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "report_swarm_findings"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Report completed swarm findings to the orchestrator. "
        "Call when coverage reaches 70%+, all priority tasks are complete, "
        "or conditions require stopping early."
    )
    incident_id: str
    zones_assessed: list[_ZoneAssessmentInput]
    survivor_detections: list[_SurvivorDetectionInput]
    hazard_map: list[_HazardMapEntryInput]
    coverage_pct: float = Field(ge=0.0, le=100.0)
    notes: str = Field(default="")


# ---------------------------------------------------------------------------
# Agent 3 tools
# ---------------------------------------------------------------------------

class _ExclusionZoneInput(BaseModel):
    lat: float
    lon: float
    radius_m: float = Field(gt=0.0)
    reason: str = Field(description="Plain-language reason humans must not enter")


class IssueAdvisoryInput(ToolInput):
    TOOL_NAME: ClassVar[str] = "issue_advisory"
    TOOL_DESCRIPTION: ClassVar[str] = (
        "Issue a structured response advisory for human first responders. "
        "You MUST call this tool — do not respond with plain text."
    )
    situation_summary: str = Field(description="2-3 sentences: what is happening, where, how severe")
    immediate_actions: list[str] = Field(
        description="Next 15 minutes only. Max 5 numbered items. Be specific.",
        max_length=5,
    )
    exclusion_zones: list[_ExclusionZoneInput]
    resource_requirements: list[str] = Field(
        description="Specific personnel and equipment. No vague requests."
    )
    risk_flags: list[str] = Field(
        description="What could deteriorate and why. Prioritize highest-consequence scenarios."
    )
    monitoring_status: str = Field(
        description="What the drone swarm is watching and at what update frequency"
    )


# ---------------------------------------------------------------------------
# Tool sets per agent (for passing to Claude API)
# ---------------------------------------------------------------------------

AGENT_1_TOOLS: list[dict] = [
    FlyToInput.to_claude_tool_dict(),
    LoiterOverInput.to_claude_tool_dict(),
    GetSensorReadingInput.to_claude_tool_dict(),
    ReportClassificationInput.to_claude_tool_dict(),
    RequestDetailedPassInput.to_claude_tool_dict(),
]

AGENT_2_TOOLS: list[dict] = [
    DeploySwarmInput.to_claude_tool_dict(),
    GetSensorReadingInput.to_claude_tool_dict(),
    UpdateZoneClassificationInput.to_claude_tool_dict(),
    MarkSurvivorInput.to_claude_tool_dict(),
    MarkHazardInput.to_claude_tool_dict(),
    ReportSwarmFindingsInput.to_claude_tool_dict(),
]

AGENT_3_TOOLS: list[dict] = [
    IssueAdvisoryInput.to_claude_tool_dict(),
]
