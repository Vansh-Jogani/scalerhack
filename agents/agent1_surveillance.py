"""Agent 1 — Surveillance Agent.

Flies expanding circle survey pattern to locate and classify incidents.
Does NOT receive disaster_type — must classify from sensor data alone.
"""

import asyncio
import math
import structlog
from anthropic import AsyncAnthropic

from prompts import load_prompt
from agents.tools.schemas import (
    AGENT_1_TOOLS,
    FlyToInput,
    GetSensorReadingInput,
    ReportClassificationInput,
)
from agents.tools.flight_tools import create_fly_to_handler
from agents.tools.sensor_tools import create_get_sensor_reading_handler
from agents.tools.report_tools import create_report_classification_handler

logger = structlog.get_logger()

SURVEY_RADII = [50.0, 100.0, 150.0]
ORBIT_POINTS = 8


def _compute_orbit_point(center_lat, center_lon, radius_m, angle_deg):
    """Compute a point on a circle at given radius and angle from center."""
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

        self._prompt = load_prompt("agent1_surveillance")

        self._tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "report_classification": create_report_classification_handler(orchestrator),
        }

        self.target_coords = None
        self.survey_state = "IDLE"
        self.current_radius_idx = 0
        self.current_orbit_point = 0
        self.sensor_readings = []
        self.classification_reported = False

    async def receive_go(self, payload: dict):
        """Receive GO signal (coordinates only) and start survey."""
        self.target_coords = payload["coordinates"]
        self.survey_state = "TRANSIT"
        self.current_radius_idx = 0
        self.current_orbit_point = 0
        self.sensor_readings = []
        self.classification_reported = False
        logger.info("agent1_go_received", coords=self.target_coords)
        asyncio.create_task(self._run_survey())

    async def _run_survey(self):
        """Execute the expanding circle survey pattern."""
        self._running = True
        center_lat = self.target_coords["lat"]
        center_lon = self.target_coords["lon"]
        cruise_alt = 120.0

        self.survey_state = "TRANSIT"
        await self._tool_handlers["fly_to"](
            drone_id=self.drone_id, lat=center_lat, lon=center_lon, alt=cruise_alt
        )
        logger.info("agent1_transit_started", target=self.target_coords)
        await self._wait_for_arrival(center_lat, center_lon)

        self.survey_state = "SURVEYING"
        for radius_idx, radius in enumerate(SURVEY_RADII):
            self.current_radius_idx = radius_idx
            orbit_readings = []

            for point_idx in range(ORBIT_POINTS):
                if not self._running:
                    return
                self.current_orbit_point = point_idx
                angle = (360.0 / ORBIT_POINTS) * point_idx
                pt_lat, pt_lon = _compute_orbit_point(center_lat, center_lon, radius, angle)

                await self._tool_handlers["fly_to"](
                    drone_id=self.drone_id, lat=pt_lat, lon=pt_lon, alt=cruise_alt
                )
                await self._wait_for_arrival(pt_lat, pt_lon)

                reading = await self._tool_handlers["get_sensor_reading"](drone_id=self.drone_id)
                orbit_readings.append(reading)

                if reading.get("status") == "ok":
                    logger.info("agent1_sensor_hit", radius=radius, point=point_idx, data=reading["data"])

            hits = [r for r in orbit_readings if r.get("status") == "ok"]
            if hits:
                self.sensor_readings = hits
                logger.info("agent1_area_confirmed", radius=radius, hits=len(hits))
                await self._classify(center_lat, center_lon, radius, hits)
                self.survey_state = "LOITERING"
                return

        logger.warning("agent1_no_sensor_data", radii_tried=SURVEY_RADII)
        self.survey_state = "COMPLETE_NO_DATA"

    async def _classify(self, center_lat, center_lon, radius, sensor_hits):
        """Use LLM to classify the incident from sensor data."""
        sensor_data = [h["data"] for h in sensor_hits]

        observations = {
            "survey_center": {"lat": center_lat, "lon": center_lon},
            "confirmed_radius_m": radius,
            "sensor_readings": sensor_data,
            "drone_telemetry": self.world_state.get_drone_telemetry(self.drone_id).__dict__,
        }

        messages = [
            {
                "role": "user",
                "content": (
                    f"Survey complete. Classify this incident from sensor data:\n\n"
                    f"{observations}"
                ),
            }
        ]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self._prompt["text"],
            messages=messages,
            tools=AGENT_1_TOOLS,
        )

        logger.info(
            "agent1_classify_called",
            prompt_version=self._prompt["version_hash"],
            stop_reason=response.stop_reason,
        )

        for block in response.content:
            if block.type == "tool_use":
                _, err = ReportClassificationInput.validate_call(block.input)
                if err:
                    logger.error("agent1_invalid_tool_call", tool=block.name, error=err)
                    continue
                handler = self._tool_handlers.get(block.name)
                if handler:
                    result = await handler(**block.input)
                    logger.info("agent1_tool_call", tool=block.name, result=result)
                    if block.name == "report_classification":
                        self.classification_reported = True

    async def _wait_for_arrival(self, target_lat, target_lon, threshold_m=20.0):
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
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
