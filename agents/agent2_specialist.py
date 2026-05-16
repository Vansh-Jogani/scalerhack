"""Agent 2 — Specialist Swarm Agent."""

import asyncio
import math
import structlog
from anthropic import AsyncAnthropic

from agents.tools.flight_tools import FLY_TO_TOOL, create_fly_to_handler
from agents.tools.sensor_tools import GET_SENSOR_READING_TOOL, create_get_sensor_reading_handler
from prompts.registry import load_prompt, fill_template

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
            "incident_id": {"type": "string"},
            "zones_assessed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string"},
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
            "coverage_pct": {"type": "number"},
            "notes": {"type": "string"},
        },
        "required": ["incident_id", "zones_assessed", "survivor_detections", "hazard_map", "coverage_pct", "notes"],
    },
}


def _haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class SpecialistAgent:
    """Agent 2: deploys specialist swarm, assesses zones, reports findings."""

    def __init__(
        self,
        agent_id: str,
        model: str,
        world_state,
        sensor_overlay,
        orchestrator,
        classification: str,
        incident_id: str = "",
        stream_callback=None,
        staging_lat: float | None = None,
        staging_lon: float | None = None,
    ):
        self.agent_id = agent_id
        self.model = model
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.orchestrator = orchestrator
        self.classification = classification
        self.incident_id = incident_id
        self.stream_callback = stream_callback
        self.staging_lat = staging_lat
        self.staging_lon = staging_lon
        self.client = AsyncAnthropic()
        self._running = False
        self._readings: dict[str, list] = {}

        self.swarm_config = SWARM_CAPABILITIES.get(classification, SWARM_CAPABILITIES["fire"])
        self.drone_ids: list[str] = []

        prompt_data = load_prompt("agent2_specialist")
        self._prompt_version_hash = prompt_data["version_hash"]
        self.system_prompt = fill_template(
            prompt_data["text"],
            swarm_type=self.swarm_config["swarm"],
            drone_count=str(self.swarm_config["drones"]),
            classification=classification,
            sensors=", ".join(self.swarm_config["sensors"]),
            altitude=str(self.swarm_config["altitude"]),
            constraint=self.swarm_config["constraint"],
            priority_tasks="\n".join(f"- {t}" for t in self.swarm_config["priority_tasks"]),
        )

        self.tools = [FLY_TO_TOOL, GET_SENSOR_READING_TOOL, REPORT_FINDINGS_TOOL]
        self._tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "report_findings": self._create_report_findings_handler(),
        }

    def _create_report_findings_handler(self):
        async def report_findings(**kwargs) -> dict:
            kwargs_with_hash = {**kwargs, "prompt_version_hash": self._prompt_version_hash}
            if not kwargs_with_hash.get("incident_id"):
                kwargs_with_hash["incident_id"] = self.incident_id
            self.orchestrator.receive_agent2_report(kwargs_with_hash)
            return {"status": "ok", "message": "Findings reported to orchestrator"}
        return report_findings

    async def _emit(self, event: str, content) -> None:
        if self.stream_callback:
            await self.stream_callback(
                "agent_stream",
                {"agent_id": self.agent_id, "event": event, "content": content},
            )

    async def run(self, agent1_report: dict) -> None:
        self._running = True
        area = agent1_report.get("area", {})
        center = area.get("center", {})
        center_lat = center.get("lat", 17.3950)
        center_lon = center.get("lon", 78.4967)
        radius_m = area.get("radius_m", 200.0)

        swarm_name = self.swarm_config["swarm"]
        if "micro" in swarm_name:
            drone_type = "micro_rotary"
        elif "fixed_wing" in swarm_name or "endurance" in swarm_name:
            drone_type = "fixed_wing"
        else:
            drone_type = "rotary"

        num_drones = self.swarm_config["drones"]
        staging_lat = self.staging_lat if self.staging_lat is not None else center_lat + 0.009
        staging_lon = self.staging_lon if self.staging_lon is not None else center_lon
        for i in range(num_drones):
            drone_id = f"swarm-{self.agent_id}-{i}"
            offset_lon = staging_lon + (i - num_drones // 2) * 0.0008
            self.world_state.add_drone(drone_id, drone_type, staging_lat, offset_lon)
            self.drone_ids.append(drone_id)
            self._readings[drone_id] = []

        await self._emit("swarm_deployed", {"drones": self.drone_ids, "type": drone_type, "count": num_drones})

        grid = self._generate_survey_grid(center_lat, center_lon, radius_m)
        assignments: dict[str, list] = {did: [] for did in self.drone_ids}
        for idx, point in enumerate(grid):
            assignments[self.drone_ids[idx % num_drones]].append(point)

        await asyncio.gather(*[
            self._survey_zone(drone_id, points) for drone_id, points in assignments.items()
        ])

        for drone_id in self.drone_ids:
            drone = self.world_state.drones.get(drone_id)
            if drone and drone.get_state() not in ("IDLE", "RTL"):
                drone.return_to_launch()

        all_readings = [r for did in self.drone_ids for r in self._readings.get(did, [])]
        await self._emit("survey_complete", {"total_readings": len(all_readings)})
        await self._report_via_llm(agent1_report, all_readings)
        self._running = False

    def _generate_survey_grid(self, center_lat, center_lon, radius_m):
        points = []
        step = radius_m / 2.0
        for dlat_steps in [-1, 0, 1]:
            for dlon_steps in [-1, 0, 1]:
                dlat = math.degrees(dlat_steps * step / 6_371_000.0)
                dlon = math.degrees(dlon_steps * step / (6_371_000.0 * math.cos(math.radians(center_lat))))
                points.append({"lat": center_lat + dlat, "lon": center_lon + dlon})
        return points

    async def _survey_zone(self, drone_id: str, waypoints: list) -> None:
        alt = float(self.swarm_config["altitude"])
        for wp in waypoints:
            if not self._running:
                return
            await self._tool_handlers["fly_to"](drone_id=drone_id, lat=wp["lat"], lon=wp["lon"], alt=alt)
            await self._wait_for_arrival(drone_id, wp["lat"], wp["lon"])
            reading = await self._tool_handlers["get_sensor_reading"](drone_id=drone_id)
            self._readings[drone_id].append(reading)

    async def _wait_for_arrival(self, drone_id, target_lat, target_lon, threshold_m=30.0):
        while self._running:
            telemetry = self.world_state.get_drone_telemetry(drone_id)
            if telemetry is None:
                await asyncio.sleep(0.5)
                continue
            if _haversine(telemetry.lat, telemetry.lon, target_lat, target_lon) < threshold_m:
                return
            await asyncio.sleep(0.3)

    async def _report_via_llm(self, agent1_report: dict, all_readings: list) -> None:
        observations = {
            "incident_id": self.incident_id,
            "agent1_report": agent1_report,
            "swarm_config": {k: v for k, v in self.swarm_config.items() if k != "priority_tasks"},
            "sensor_readings": all_readings[:20],
            "drones_deployed": self.drone_ids,
        }
        messages = [{"role": "user", "content": f"Swarm assessment complete. Compile findings and call report_findings:\n{observations}"}]
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages,
            tools=self.tools,
        )
        for block in response.content:
            if block.type == "tool_use":
                handler = self._tool_handlers.get(block.name)
                if handler:
                    result = await handler(**block.input)
                    logger.info("agent2_tool_call", tool=block.name, result=result)
                    if block.name == "report_findings":
                        await self._emit("findings_reported", block.input)

    def stop(self) -> None:
        self._running = False
