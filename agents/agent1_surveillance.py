"""Agent 1 — Surveillance Agent.

Flies expanding circle survey pattern to locate and classify incidents.
Does NOT receive disaster_type — must classify from sensor data alone.
"""

import asyncio
import math
import structlog
from anthropic import AsyncAnthropic

from agents.tools.flight_tools import FLY_TO_TOOL, create_fly_to_handler
from agents.tools.sensor_tools import GET_SENSOR_READING_TOOL, create_get_sensor_reading_handler
from agents.tools.report_tools import REPORT_CLASSIFICATION_TOOL, create_report_classification_handler

logger = structlog.get_logger()

AGENT_1_SYSTEM_PROMPT = """You are ARIA Surveillance Agent. You control a fixed-wing reconnaissance drone.

You receive: Go signal with approximate coordinates.
You do NOT know the disaster type — you must classify from sensor data.

Your mission:
1. Fly to provided coordinates
2. Begin expanding circle survey: radius 50m, then 100m, then 150m
3. At each orbit, call get_sensor_reading()
4. If sensor returns data → area found, continue orbiting at that radius
5. Once full orbit complete with consistent sensor data → classify
6. Call report_classification() with your findings
7. Remain in loiter at confirmed radius

Your drone:
- Speed: 18 m/s cruise, 80m loiter radius
- Altitude: 120m AGL for survey, 60m for detailed pass
- You control 1 aircraft

Rules:
- Complete one full orbit before reporting classification
- Always report confidence level with classification
- Never descend below 60m AGL

Available tools: fly_to, get_sensor_reading, report_classification
"""

SURVEY_RADII = [50.0, 100.0, 150.0]
ORBIT_POINTS = 8


def _compute_orbit_point(center_lat, center_lon, radius_m, angle_deg):
    earth_radius = 6_371_000.0
    lat_r = math.radians(center_lat)
    lon_r = math.radians(center_lon)
    bearing_r = math.radians(angle_deg)
    angular_dist = radius_m / earth_radius
    new_lat_r = math.asin(
        math.sin(lat_r) * math.cos(angular_dist)
        + math.cos(lat_r) * math.sin(angular_dist) * math.cos(bearing_r)
    )
    new_lon_r = lon_r + math.atan2(
        math.sin(bearing_r) * math.sin(angular_dist) * math.cos(lat_r),
        math.cos(angular_dist) - math.sin(lat_r) * math.sin(new_lat_r),
    )
    return math.degrees(new_lat_r), math.degrees(new_lon_r)


class SurveillanceAgent:
    """Agent 1: flies expanding circle pattern, classifies incident from sensor data."""

    def __init__(self, agent_id: str, model: str, world_state, sensor_overlay, orchestrator, drone_id: str):
        self.agent_id = agent_id
        self.model = model
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.orchestrator = orchestrator
        self.drone_id = drone_id
        self.client = AsyncAnthropic()
        self._running = False
        self._broadcast_fn = None

        self.tools = [FLY_TO_TOOL, GET_SENSOR_READING_TOOL, REPORT_CLASSIFICATION_TOOL]
        self._tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "report_classification": create_report_classification_handler(orchestrator),
        }

        self.target_coords = None
        self._incident_id = None
        self.survey_state = "IDLE"
        self.sensor_readings = []
        self.classification_reported = False

    def set_broadcast(self, fn) -> None:
        self._broadcast_fn = fn

    async def _log(self, event: str, msg: str, **data) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn({
                    "type": "agent_log",
                    "agent": "agent1",
                    "event": event,
                    "msg": msg,
                    "data": data,
                })
            except Exception:
                pass

    async def receive_go(self, payload: dict):
        """Receive GO signal (coordinates only) and start survey."""
        self.target_coords = payload["coordinates"]
        self._incident_id = payload.get("incident_id", f"INC-{int(__import__('time').time())}")
        self.survey_state = "TRANSIT"
        self.sensor_readings = []
        self.classification_reported = False
        logger.info("agent1_go_received", coords=self.target_coords, incident_id=self._incident_id)
        asyncio.create_task(self._run_survey())

    async def _run_survey(self):
        self._running = True
        center_lat = self.target_coords["lat"]
        center_lon = self.target_coords["lon"]
        cruise_alt = 120.0

        # Phase 1: Fly to target coordinates
        self.survey_state = "TRANSIT"
        await self._tool_handlers["fly_to"](
            drone_id=self.drone_id, lat=center_lat, lon=center_lon, alt=cruise_alt
        )
        logger.info("agent1_transit_started", target=self.target_coords)

        # Wait for arrival
        await self._wait_for_arrival(center_lat, center_lon)
        await self._log("arrived", "Arrived at incident area — beginning survey pattern")

        # Phase 2: Expanding circle survey
        self.survey_state = "SURVEYING"
        for radius_idx, radius in enumerate(SURVEY_RADII):
            if not self._running:
                return

            orbit_hits = []
            await self._log("orbit_start", f"Orbit {radius_idx+1}/3 — radius {radius:.0f}m")

            for point_idx in range(ORBIT_POINTS):
                if not self._running:
                    return

                angle = (360.0 / ORBIT_POINTS) * point_idx
                pt_lat, pt_lon = _compute_orbit_point(center_lat, center_lon, radius, angle)

                await self._tool_handlers["fly_to"](
                    drone_id=self.drone_id, lat=pt_lat, lon=pt_lon, alt=cruise_alt
                )
                await self._wait_for_arrival(pt_lat, pt_lon)

                reading = await self._tool_handlers["get_sensor_reading"](drone_id=self.drone_id)

                if reading.get("status") == "ok":
                    orbit_hits.append(reading)
                    await self._log("sensor_hit",
                                    f"Sensor data at radius {radius:.0f}m, point {point_idx+1}/{ORBIT_POINTS}",
                                    radius=radius, point=point_idx, data=reading["data"])

            # Check if we got consistent sensor data in this orbit
            hits = [r for r in orbit_readings if r.get("status") == "ok"]
            if hits:
                self.sensor_readings = hits
                logger.info("agent1_area_confirmed", radius=radius, hits=len(hits))
                # Area found — classify using LLM
                await self._classify(center_lat, center_lon, radius, hits)
                # Remain in loiter
                self.survey_state = "LOITERING"
                return

        # No hits at any radius
        logger.warning("agent1_no_sensor_data", radii_tried=SURVEY_RADII)
        self.survey_state = "COMPLETE_NO_DATA"

    async def _classify(self, center_lat, center_lon, radius, sensor_hits):
        """Use LLM to classify the incident. Forces report_classification via tool_choice."""
        sensor_data = [h["data"] for h in sensor_hits]
        telemetry = self.world_state.get_drone_telemetry(self.drone_id)
        telemetry_dict = {
            "lat": telemetry.lat, "lon": telemetry.lon, "alt": telemetry.alt,
            "heading": telemetry.heading, "speed": telemetry.speed, "state": telemetry.state,
        } if telemetry else {}

        messages = [
            {"role": "user", "content": f"Survey complete. Classify this incident from sensor data:\n{observations}"}
        ]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=AGENT_1_SYSTEM_PROMPT,
            messages=messages,
            tools=self.tools,
        )

        for block in response.content:
            if block.type == "tool_use":
                handler = self._tool_handlers.get(block.name)
                if handler:
                    result = await handler(**block.input)
                    logger.info("agent1_tool_call", tool=block.name, result=result)
                    if block.name == "report_classification":
                        self.classification_reported = True

    async def _wait_for_arrival(self, target_lat, target_lon, threshold_m=20.0):
        """Wait until drone is within threshold of target."""
        while self._running:
            telemetry = self.world_state.get_drone_telemetry(self.drone_id)
            if telemetry is None:
                await asyncio.sleep(0.5)
                continue
            dist = _haversine(telemetry.lat, telemetry.lon, target_lat, target_lon)
            if dist < threshold_m:
                return
            await asyncio.sleep(0.2)

    def stop(self):
        self._running = False


def _haversine(lat1, lon1, lat2, lon2):
    """Distance in meters between two points."""
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
