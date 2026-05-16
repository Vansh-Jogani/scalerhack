"""Agent 2 — Specialist Swarm Agent.

Inherits BaseAgent. Receives swarm_config from orchestrator via classifier.py.
Does NOT choose its own swarm type — that is enforced by code structure:
swarm_config is a required constructor parameter, not derived internally.

Per SPEC.md:
- Swarm selection is locked to a decision table in code (classifier.py)
- Agent reasons within the chosen config — does not choose it
- Tools: fly_to, loiter_over, get_sensor_reading, zone_annotate, survivor_marker, report_findings
- Writes findings to state.map_layers only
"""

import asyncio
import json
import math
from pathlib import Path
import structlog

from agents.base_agent import BaseAgent
from agents.tools.flight_tools import (
    FLY_TO_TOOL,
    LOITER_OVER_TOOL,
    create_fly_to_handler,
    create_loiter_over_handler,
)
from agents.tools.sensor_tools import (
    GET_SENSOR_READING_TOOL,
    create_get_sensor_reading_handler,
)
from agents.tools.report_tools import (
    ZONE_ANNOTATE_TOOL,
    SURVIVOR_MARKER_TOOL,
    REPORT_FINDINGS_TOOL,
    create_zone_annotate_handler,
    create_survivor_marker_handler,
    create_report_findings_handler,
)

logger = structlog.get_logger()

AGENT_2_SYSTEM_PROMPT_TEMPLATE = """You are ARIA Specialist Swarm Agent. You control a {swarm_type} swarm of {drone_count} drones.

Incident classification: {classification}
Swarm type: {swarm_type}
Sensors available: {sensors}
Operating altitude: {altitude}m AGL
Operational constraint: {constraint}

Priority tasks (execute in order):
{priority_tasks}

Your mission:
1. Deploy your swarm drones to cover the incident area systematically
2. Execute priority tasks in the order listed above
3. Use zone_annotate to label each assessed zone
4. Use survivor_marker when thermal or acoustic signatures indicate survivors
5. Call report_findings when you have covered sufficient area

Rules:
- Enforce your operational constraint at all times
- Never exceed your assigned altitude
- Annotate every zone you assess — do not skip
- Report findings when coverage reaches 70% or all priority tasks are complete

Available tools: fly_to, loiter_over, get_sensor_reading, zone_annotate, survivor_marker, report_findings
"""


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_response_centres() -> list[dict]:
    """Load response centres from the shared JSON file."""
    candidates = [
        Path(__file__).parent.parent / "frontend" / "src" / "data" / "response_centres.json",
        Path("frontend/src/data/response_centres.json"),
    ]
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return []


def _nearest_response_centre(lat: float, lon: float) -> dict:
    """Return the nearest response centre to the given coordinates."""
    centres = _load_response_centres()
    if not centres:
        # Fallback: Hyderabad city centre
        return {"lat": 17.3850, "lon": 78.4867, "name": "default"}
    return min(centres, key=lambda c: _haversine(lat, lon, c["lat"], c["lon"]))


class SpecialistAgent(BaseAgent):
    """Agent 2: Specialist Swarm — deploys swarm, assesses zones, reports findings.

    Inherits BaseAgent OODA-R loop.
    swarm_config is injected by the orchestrator from classifier.py — never self-selected.
    """

    def __init__(
        self,
        agent_id: str,
        model: str,
        world_state,
        sensor_overlay,
        orchestrator,
        swarm_config: dict,       # injected by orchestrator — NOT self-selected
        classification: str,
        stream_callback=None,
    ):
        # swarm_config comes from classifier.py via orchestrator — Agent 2 never looks it up
        self.swarm_config = swarm_config
        self.classification = classification
        self.orchestrator = orchestrator

        system_prompt = AGENT_2_SYSTEM_PROMPT_TEMPLATE.format(
            swarm_type=swarm_config["swarm"],
            drone_count=swarm_config["drones"],
            classification=classification,
            sensors=", ".join(swarm_config["sensors"]),
            altitude=swarm_config["altitude"],
            constraint=swarm_config["constraint"],
            priority_tasks="\n".join(f"- {t}" for t in swarm_config["priority_tasks"]),
        )

        tools = [
            FLY_TO_TOOL,
            LOITER_OVER_TOOL,
            GET_SENSOR_READING_TOOL,
            ZONE_ANNOTATE_TOOL,
            SURVIVOR_MARKER_TOOL,
            REPORT_FINDINGS_TOOL,
        ]

        tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "loiter_over": create_loiter_over_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "zone_annotate": create_zone_annotate_handler(),
            "survivor_marker": create_survivor_marker_handler(),
            "report_findings": create_report_findings_handler(
                orchestrator,
                stream_callback=stream_callback,
                agent_id=agent_id,
            ),
        }

        super().__init__(
            agent_id=agent_id,
            system_prompt=system_prompt,
            model=model,
            world_state=world_state,
            sensor_overlay=sensor_overlay,
            drone_ids=[],           # populated in run_mission after drones are spawned
            tools=tools,
            tool_handlers=tool_handlers,
            interval=2.0,
            stream_callback=stream_callback,
        )

    async def run_mission(self, agent1_report: dict) -> None:
        """Spawn swarm drones, fly survey grid, then hand off to LLM for findings.

        Called by orchestrator._swarm_node(). Matches the orchestrator call site.
        """
        area = agent1_report.get("area", {})
        center = area.get("center", {})
        center_lat = center.get("lat", 17.3950)
        center_lon = center.get("lon", 78.4967)
        radius_m = area.get("radius_m", 200.0)

        # Determine drone type from swarm name
        swarm_name = self.swarm_config["swarm"]
        if "micro" in swarm_name:
            drone_type = "micro_rotary"
        elif "fixed_wing" in swarm_name or "endurance" in swarm_name:
            drone_type = "fixed_wing"
        else:
            drone_type = "rotary"

        # Spawn swarm drones from the nearest response centre to the incident
        nearest = _nearest_response_centre(center_lat, center_lon)
        spawn_lat = nearest["lat"]
        spawn_lon = nearest["lon"]
        logger.info("swarm_spawn_origin", centre=nearest.get("name", "unknown"),
                    lat=spawn_lat, lon=spawn_lon)

        num_drones = self.swarm_config["drones"]
        for i in range(num_drones):
            drone_id = f"swarm-{self.agent_id}-{i}"
            # Spread drones slightly so they don't stack on the same pixel
            offset_lon = spawn_lon + (i - num_drones // 2) * 0.0008
            self.world_state.add_drone(drone_id, drone_type, spawn_lat, offset_lon)
            self.drone_ids.append(drone_id)
            logger.info("swarm_drone_spawned", drone_id=drone_id, type=drone_type)

        await self._emit("swarm_deployed", {
            "drones": self.drone_ids,
            "type": drone_type,
            "count": num_drones,
            "swarm": swarm_name,
        })

        # Fly survey grid concurrently across all drones
        grid = self._generate_survey_grid(center_lat, center_lon, radius_m)
        assignments: dict[str, list] = {did: [] for did in self.drone_ids}
        for idx, point in enumerate(grid):
            assignments[self.drone_ids[idx % num_drones]].append(point)

        readings: dict[str, list] = {did: [] for did in self.drone_ids}
        await asyncio.gather(*[
            self._survey_zone(drone_id, points, readings)
            for drone_id, points in assignments.items()
        ])

        # Compile all readings and hand to LLM for zone annotation + report
        all_readings = [r for did in self.drone_ids for r in readings.get(did, [])]
        await self._emit("survey_complete", {
            "total_readings": len(all_readings),
            "drones": len(self.drone_ids),
        })

        # Build initial message for the LLM to compile findings and call tools
        initial_msg = (
            f"Swarm survey complete. Classification: {self.classification}. "
            f"Swarm type: {self.swarm_config['swarm']}. "
            f"Drones deployed: {self.drone_ids}. "
            f"Sensor readings collected: {len(all_readings)}. "
            f"Sample readings (first 10): {all_readings[:10]}. "
            f"Agent 1 report: {agent1_report}. "
            f"Now: annotate all assessed zones with zone_annotate, mark any survivors with "
            f"survivor_marker, then call report_findings with complete findings."
        )

        # Run the BaseAgent OODA-R loop for the LLM reasoning + tool calls phase
        await self.run(initial_message=initial_msg)

    def _generate_survey_grid(
        self, center_lat: float, center_lon: float, radius_m: float
    ) -> list[dict]:
        """3×3 grid of waypoints within incident radius."""
        points = []
        step = radius_m / 2.0
        for dlat_steps in [-1, 0, 1]:
            for dlon_steps in [-1, 0, 1]:
                dlat = math.degrees(dlat_steps * step / 6_371_000.0)
                dlon = math.degrees(
                    dlon_steps * step / (6_371_000.0 * math.cos(math.radians(center_lat)))
                )
                points.append({"lat": center_lat + dlat, "lon": center_lon + dlon})
        return points

    async def _survey_zone(
        self, drone_id: str, waypoints: list, readings: dict
    ) -> None:
        """Fly a drone through its assigned waypoints, collecting sensor readings."""
        alt = float(self.swarm_config["altitude"])
        fly_to = self._tool_handlers["fly_to"]
        get_reading = self._tool_handlers["get_sensor_reading"]

        for wp in waypoints:
            if not self._running and self._running is not None:
                return
            await fly_to(drone_id=drone_id, lat=wp["lat"], lon=wp["lon"], alt=alt)
            await self._wait_for_arrival(drone_id, wp["lat"], wp["lon"])
            reading = await get_reading(drone_id=drone_id)
            readings[drone_id].append(reading)

    async def _wait_for_arrival(
        self,
        drone_id: str,
        target_lat: float,
        target_lon: float,
        threshold_m: float = 30.0,
        timeout_s: float = 120.0,
    ) -> None:
        """Poll telemetry until drone is within threshold_m of target, or timeout."""
        elapsed = 0.0
        interval = 0.3
        while elapsed < timeout_s:
            telemetry = self.world_state.get_drone_telemetry(drone_id)
            if telemetry is not None:
                dist = _haversine(telemetry.lat, telemetry.lon, target_lat, target_lon)
                if dist < threshold_m:
                    return
            await asyncio.sleep(interval)
            elapsed += interval
        logger.warning("arrival_timeout", drone_id=drone_id, target_lat=target_lat, target_lon=target_lon)
