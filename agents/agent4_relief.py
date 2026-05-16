"""Agent 4 — Relief Coordinator.

Spawns disaster-type-specific relief drones at the response centre,
calls Claude to produce a structured relief plan with waypoints,
then commands each drone to its assigned relief position.
"""

import asyncio
import structlog
from anthropic import AsyncAnthropic

from agents.tools.flight_tools import create_fly_to_handler
from prompts.registry import load_prompt

logger = structlog.get_logger()

RELIEF_CONFIGS = {
    "fire": {
        "relief_type": "fire_suppression",
        "drones": 2,
        "drone_type": "rotary",
        "altitude": 40,
    },
    "structural_collapse": {
        "relief_type": "passage_discovery",
        "drones": 2,
        "drone_type": "micro_rotary",
        "altitude": 10,
    },
    "flood": {
        "relief_type": "drainage_survey",
        "drones": 1,
        "drone_type": "fixed_wing",
        "altitude": 80,
    },
    "industrial_hazard": {
        "relief_type": "hazard_containment",
        "drones": 2,
        "drone_type": "rotary",
        "altitude": 80,
    },
    "maritime_sar": {
        "relief_type": "rescue_coordination",
        "drones": 2,
        "drone_type": "fixed_wing",
        "altitude": 120,
    },
}

COORDINATE_RELIEF_TOOL = {
    "name": "coordinate_relief",
    "description": "Issue post-assessment relief coordination plan with drone tasking.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "relief_type": {"type": "string"},
            "actions": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "priority": {"type": "string", "enum": ["immediate", "high", "medium"]},
                        "action": {"type": "string"},
                        "details": {"type": "string"},
                    },
                    "required": ["priority", "action", "details"],
                },
            },
            "drone_waypoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                    },
                    "required": ["role", "lat", "lon"],
                },
            },
            "alerts": {
                "type": "array",
                "items": {"type": "string"},
            },
            "resource_requests": {
                "type": "array",
                "items": {"type": "string"},
            },
            "status": {"type": "string"},
        },
        "required": [
            "incident_id", "relief_type", "actions",
            "drone_waypoints", "alerts", "resource_requests", "status",
        ],
    },
}


class ReliefAgent:
    """Agent 4: coordinates disaster-specific relief operations after swarm assessment."""

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
        severity: str = "medium",
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
        self.severity = severity
        self.client = AsyncAnthropic()

        self.config = RELIEF_CONFIGS.get(classification, RELIEF_CONFIGS["fire"])
        self.drone_ids: list[str] = []

        prompt_data = load_prompt("agent4_relief")
        self.system_prompt = prompt_data["text"]
        self._fly_to = create_fly_to_handler(world_state)

    async def _emit(self, event: str, content) -> None:
        if self.stream_callback:
            await self.stream_callback(
                "agent_stream",
                {"agent_id": self.agent_id, "event": event, "content": content},
            )

    async def run(self, agent2_report: dict) -> None:
        area = agent2_report.get("area", {})
        center = area.get("center", {})
        center_lat = center.get("lat", 17.3950)
        center_lon = center.get("lon", 78.4967)

        staging_lat = self.staging_lat if self.staging_lat is not None else center_lat
        staging_lon = self.staging_lon if self.staging_lon is not None else center_lon

        num_drones = self.config["drones"]
        drone_type = self.config["drone_type"]
        alt = float(self.config["altitude"])

        for i in range(num_drones):
            drone_id = f"relief-{self.agent_id}-{i}"
            offset_lon = staging_lon + (i - num_drones // 2) * 0.0006
            self.world_state.add_drone(drone_id, drone_type, staging_lat, offset_lon)
            self.drone_ids.append(drone_id)

        await self._emit("relief_started", {
            "relief_type": self.config["relief_type"],
            "drones": self.drone_ids,
            "classification": self.classification,
        })

        context = {
            "incident_id": self.incident_id,
            "classification": self.classification,
            "center": {"lat": center_lat, "lon": center_lon},
            "zones_assessed": agent2_report.get("zones_assessed", [])[:6],
            "survivor_detections": agent2_report.get("survivor_detections", [])[:4],
            "hazard_map": agent2_report.get("hazard_map", [])[:4],
            "relief_drones_available": num_drones,
            "relief_type": self.config["relief_type"],
            "altitude_m": alt,
        }

        messages = [{"role": "user", "content": (
            f"Swarm assessment complete for {self.classification} incident. "
            f"Coordinate relief operations and assign {num_drones} drone(s) to positions:\n{context}"
        )}]

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.system_prompt,
                messages=messages,
                tools=[COORDINATE_RELIEF_TOOL],
                tool_choice={"type": "tool", "name": "coordinate_relief"},
            )
        except Exception as e:
            logger.error("agent4_llm_error", error=str(e))
            await self._fallback_plan(center_lat, center_lon, alt)
            return

        relief_plan: dict = {}
        for block in response.content:
            if block.type == "tool_use" and block.name == "coordinate_relief":
                relief_plan = dict(block.input)
                if not relief_plan.get("incident_id"):
                    relief_plan["incident_id"] = self.incident_id
                break

        if not relief_plan:
            await self._fallback_plan(center_lat, center_lon, alt)
            return

        waypoints = relief_plan.get("drone_waypoints", [])
        for i, drone_id in enumerate(self.drone_ids):
            if i < len(waypoints):
                wp = waypoints[i]
                await self._fly_to(drone_id=drone_id, lat=wp["lat"], lon=wp["lon"], alt=alt)
                await self._emit("drone_tasked", {
                    "drone_id": drone_id,
                    "role": wp.get("role", self.config["relief_type"]),
                    "lat": round(wp["lat"], 5),
                    "lon": round(wp["lon"], 5),
                })
            else:
                await self._fly_to(drone_id=drone_id, lat=center_lat, lon=center_lon, alt=alt)

        for alert in relief_plan.get("alerts", []):
            await self._emit("alert_broadcast", alert)

        await self._emit("findings_reported", relief_plan)
        self.orchestrator.receive_agent4_report(relief_plan)

        asyncio.create_task(self._suppression_sequence(waypoints))
        logger.info("agent4_relief_complete", incident_id=self.incident_id, relief_type=self.config["relief_type"])

    async def _wait_for_arrivals(self, timeout: float = 45.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            states = [
                (self.world_state.drones[did].get_state() if did in self.world_state.drones else "IDLE")
                for did in self.drone_ids
            ]
            if all(s in ("LOITERING", "IDLE", "RTL") for s in states):
                return
            await asyncio.sleep(0.5)

    async def _suppression_sequence(self, waypoints: list) -> None:
        try:
            await self._wait_for_arrivals(timeout=45.0)
            await asyncio.sleep(8)  # scope / position the area before engaging

            is_fire = self.classification == "fire"
            if is_fire:
                drop_rounds = {"low": 4, "medium": 5, "high": 6}.get(self.severity, 5)
                await self._emit("suppression_active", {
                    "incident_id": self.incident_id,
                    "drone_ids": self.drone_ids,
                    "severity": self.severity,
                })
                for _ in range(drop_rounds):
                    await asyncio.sleep(4)
                    for drone_id in self.drone_ids:
                        drone_obj = self.world_state.drones.get(drone_id)
                        spray_lat = drone_obj.lat if drone_obj else None
                        spray_lon = drone_obj.lon if drone_obj else None
                        if spray_lat is None and waypoints:
                            spray_lat = waypoints[0]["lat"]
                            spray_lon = waypoints[0]["lon"]
                        if spray_lat is None:
                            continue
                        await self._emit("suppression_drop", {
                            "drone_id": drone_id,
                            "lat": spray_lat,
                            "lon": spray_lon,
                            "incident_id": self.incident_id,
                        })
                await asyncio.sleep(12)  # post-suppression loiter / assessment
                await self._emit("suppression_complete", {
                    "incident_id": self.incident_id,
                    "severity": self.severity,
                })
            else:
                loiter_secs = {"structural_collapse": 30, "flood": 20, "industrial_hazard": 25, "maritime_sar": 20}
                await asyncio.sleep(loiter_secs.get(self.classification, 20))

            for drone_id in self.drone_ids:
                drone = self.world_state.drones.get(drone_id)
                if drone and drone.get_state() not in ("IDLE", "RTL"):
                    drone.return_to_launch()
        except Exception as e:
            logger.error("agent4_suppression_error", error=str(e), incident_id=self.incident_id)
            for drone_id in self.drone_ids:
                drone = self.world_state.drones.get(drone_id)
                if drone and drone.get_state() not in ("IDLE", "RTL"):
                    drone.return_to_launch()

    async def _fallback_plan(self, center_lat: float, center_lon: float, alt: float) -> None:
        """Fallback when LLM fails — command drones to centroid and report minimal plan."""
        for drone_id in self.drone_ids:
            await self._fly_to(drone_id=drone_id, lat=center_lat, lon=center_lon, alt=alt)
        plan = {
            "incident_id": self.incident_id,
            "relief_type": self.config["relief_type"],
            "actions": [{"priority": "immediate", "action": "Deploy to centroid", "details": "LLM fallback — drones assigned to incident centre"}],
            "drone_waypoints": [{"role": "relief", "lat": center_lat, "lon": center_lon}],
            "alerts": [],
            "resource_requests": [],
            "status": "deployed_fallback",
        }
        await self._emit("findings_reported", plan)
        self.orchestrator.receive_agent4_report(plan)
        asyncio.create_task(self._suppression_sequence([{"lat": center_lat, "lon": center_lon}]))
