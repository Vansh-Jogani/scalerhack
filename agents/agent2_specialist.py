"""Agent 2 — Specialist Swarm Agent.

Deploys specialist swarm based on swarm config selected by orchestrator.
Reports zone assessments, survivor detections, and hazard maps.
"""

import asyncio
import structlog
from anthropic import AsyncAnthropic

from agents.tools.flight_tools import FLY_TO_TOOL, create_fly_to_handler
from agents.tools.sensor_tools import GET_SENSOR_READING_TOOL, create_get_sensor_reading_handler

logger = structlog.get_logger()

SWARM_CAPABILITIES = {
    "fire": {
        "swarm": "thermal_rotary",
        "drones": 3,
        "sensors": ["thermal_camera", "gas_detector", "wind_sensor"],
        "altitude": 50,
        "speed": 8,
        "priority_tasks": ["map_fire_perimeter", "identify_hotspots", "detect_trapped_persons", "assess_spread_direction"],
        "constraint": "maintain_upwind_position",
    },
    "structural_collapse": {
        "swarm": "micro_search_rotary",
        "drones": 4,
        "sensors": ["acoustic_detector", "co2_sensor", "thermal", "visual_hd"],
        "altitude": 15,
        "speed": 4,
        "priority_tasks": ["map_void_spaces", "detect_survivors", "assess_structural_integrity", "identify_egress_paths"],
        "constraint": "avoid_zones_integrity_below_0.2",
    },
    "flood": {
        "swarm": "fixed_wing_extended",
        "drones": 2,
        "sensors": ["visual_hd", "thermal", "depth_estimation"],
        "altitude": 80,
        "speed": 18,
        "priority_tasks": ["map_flood_extent", "identify_isolated_survivors", "assess_flow_direction", "find_safe_approach_routes"],
        "constraint": "maintain_visual_line_of_sight",
    },
    "industrial_hazard": {
        "swarm": "standoff_rotary",
        "drones": 2,
        "sensors": ["gas_spectrometer", "thermal", "visual_hd"],
        "altitude": 100,
        "speed": 6,
        "priority_tasks": ["identify_hazard_source", "map_exclusion_zone", "detect_spread_direction", "assess_secondary_risk"],
        "constraint": "minimum_200m_standoff_from_source",
    },
    "maritime_sar": {
        "swarm": "fixed_wing_endurance",
        "drones": 3,
        "sensors": ["visual_hd", "thermal", "ais_receiver"],
        "altitude": 150,
        "speed": 22,
        "priority_tasks": ["expanding_square_search", "detect_persons_in_water", "track_drift_objects", "coordinate_vessel_response"],
        "constraint": "maintain_comms_relay_chain",
    },
}

REPORT_FINDINGS_TOOL = {
    "name": "report_findings",
    "description": "Report specialist swarm findings to orchestrator. Call after completing zone assessment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string", "description": "Incident ID from Agent 1 report"},
            "zones_assessed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string", "description": "Zone ID in format ZONE-{lat}-{lon}"},
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "findings": {
                            "type": "object",
                            "properties": {
                                "thermal_signatures": {"type": "integer"},
                                "structural_integrity": {"type": "number"},
                                "hazards_detected": {"type": "array", "items": {"type": "string"}},
                                "survivor_count": {"type": "integer"},
                            },
                            "required": ["thermal_signatures", "structural_integrity", "hazards_detected", "survivor_count"],
                        },
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "actionable": {"type": "boolean"},
                    },
                    "required": ["zone_id", "lat", "lon", "findings", "risk_level", "actionable"],
                },
            },
            "survivor_detections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["lat", "lon", "confidence"],
                },
            },
            "hazard_map": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "type": {"type": "string"},
                        "exclusion_radius_m": {"type": "number"},
                    },
                    "required": ["lat", "lon", "type", "exclusion_radius_m"],
                },
            },
            "coverage_pct": {"type": "number", "description": "Percentage of area covered 0-100"},
            "notes": {"type": "string"},
        },
        "required": ["incident_id", "zones_assessed", "survivor_detections", "hazard_map", "coverage_pct", "notes"],
    },
}


def create_report_findings_handler(orchestrator):
    async def report_findings(**kwargs) -> dict:
        orchestrator.receive_agent2_report(kwargs)
        return {"status": "ok", "message": "Findings reported to orchestrator"}
    return report_findings


AGENT_2_SYSTEM_PROMPT_TEMPLATE = """You are ARIA Specialist Swarm Agent. You control a {swarm_type} swarm of {drone_count} drones.

Incident classification: {classification}
Swarm config: {swarm_type}
Sensors available: {sensors}
Altitude: {altitude}m
Constraint: {constraint}

Priority tasks:
{priority_tasks}

Your mission:
1. Deploy swarm drones to cover the incident area
2. Execute priority tasks in order
3. Report zone assessments with findings
4. Track survivors and hazards
5. Report findings when coverage is sufficient

Available tools: fly_to, get_sensor_reading, report_findings
"""


class SpecialistAgent:
    """Agent 2: deploys specialist swarm, assesses zones, reports findings."""

    def __init__(self, agent_id: str, model: str, world_state, sensor_overlay, orchestrator, classification: str):
        self.agent_id = agent_id
        self.model = model
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.orchestrator = orchestrator
        self.classification = classification
        self.client = AsyncAnthropic()
        self._running = False
        self._broadcast_fn = None

    def set_broadcast(self, fn) -> None:
        self._broadcast_fn = fn

    async def _log(self, event: str, msg: str, **data) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn({
                    "type": "agent_log", "agent": "agent2",
                    "event": event, "msg": msg, "data": data,
                })
            except Exception:
                pass

        self.swarm_config = SWARM_CAPABILITIES[classification]
        self.drone_ids = []

        self.tools = [FLY_TO_TOOL, GET_SENSOR_READING_TOOL, REPORT_FINDINGS_TOOL]
        self._tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "report_findings": create_report_findings_handler(orchestrator),
        }

        self.system_prompt = AGENT_2_SYSTEM_PROMPT_TEMPLATE.format(
            swarm_type=self.swarm_config["swarm"],
            drone_count=self.swarm_config["drones"],
            classification=classification,
            sensors=", ".join(self.swarm_config["sensors"]),
            altitude=self.swarm_config["altitude"],
            constraint=self.swarm_config["constraint"],
            priority_tasks="\n".join(f"- {t}" for t in self.swarm_config["priority_tasks"]),
        )

    def stop(self):
        self._running = False
