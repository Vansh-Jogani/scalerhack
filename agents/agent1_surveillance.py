"""Agent 1 — Surveillance Agent.

Flies expanding circle survey pattern to locate and classify incidents.
Does NOT receive disaster_type — classifies from sensor data alone.
After classification, makes an explicit decision: request backup or maintain surveillance.
"""

import asyncio
import math
import structlog
from anthropic import AsyncAnthropic

from agents.tools.flight_tools import FLY_TO_TOOL, create_fly_to_handler
from agents.tools.sensor_tools import GET_SENSOR_READING_TOOL, create_get_sensor_reading_handler
from agents.tools.report_tools import (
    REPORT_CLASSIFICATION_TOOL,
    REQUEST_BACKUP_TOOL,
    MAINTAIN_SURVEILLANCE_TOOL,
    create_report_classification_handler,
    create_request_backup_handler,
    create_maintain_surveillance_handler,
)
from prompts.registry import load_prompt

logger = structlog.get_logger()

SURVEY_RADII = [180.0, 300.0]  # visible on map; sensors trigger at first ring
ORBIT_POINTS = 8               # clean circle, 45° between points


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


def _haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class SurveillanceAgent:
    """Agent 1: expanding circle survey → LLM classification → decision (backup or maintain)."""

    def __init__(
        self,
        agent_id: str,
        model: str,
        world_state,
        sensor_overlay,
        orchestrator,
        drone_id: str,
        stream_callback=None,
    ):
        self.agent_id = agent_id
        self.model = model
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.orchestrator = orchestrator
        self.drone_id = drone_id
        self.stream_callback = stream_callback
        self.client = AsyncAnthropic()
        self._running = False
        self._decision = None

        prompt_data = load_prompt("agent1_surveillance")
        self._system_prompt = prompt_data["text"]
        self._prompt_version_hash = prompt_data["version_hash"]

        self.tools = [FLY_TO_TOOL, GET_SENSOR_READING_TOOL, REPORT_CLASSIFICATION_TOOL]
        self._tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "report_classification": create_report_classification_handler(orchestrator),
            "request_backup": create_request_backup_handler(orchestrator),
            "maintain_surveillance": create_maintain_surveillance_handler(orchestrator),
        }

        self.target_coords = None
        self.type_hint = "unknown"
        self.classification_reported = False
        self.sensor_readings = []

    async def _emit(self, event: str, content) -> None:
        if self.stream_callback:
            await self.stream_callback(
                "agent_stream",
                {"agent_id": self.agent_id, "event": event, "content": content},
            )

    async def receive_go(self, payload: dict) -> None:
        self.target_coords = payload["coordinates"]
        self.type_hint = payload.get("type_hint", "unknown")
        self._running = True
        self.classification_reported = False
        self.sensor_readings = []
        logger.info("agent1_go_received", coords=self.target_coords, type_hint=self.type_hint)
        await self._emit("survey_started", f"Dispatched to ({self.target_coords['lat']:.4f}, {self.target_coords['lon']:.4f}) — type_hint: {self.type_hint}")
        try:
            await self._run_survey()
        except Exception as e:
            logger.error("agent1_survey_error", error=str(e))
            await self._emit("error", {"message": str(e)})

    async def _run_survey(self) -> None:
        center_lat = self.target_coords["lat"]
        center_lon = self.target_coords["lon"]
        cruise_alt = 120.0

        await self._emit("nav", f"fly_to({center_lat:.4f}, {center_lon:.4f}, alt={cruise_alt:.0f}m) — transit to incident zone")
        await self._tool_handlers["fly_to"](
            drone_id=self.drone_id, lat=center_lat, lon=center_lon, alt=cruise_alt
        )
        await self._wait_for_arrival(center_lat, center_lon)
        await self._emit("on_station", f"Over zone ({center_lat:.4f}, {center_lon:.4f}) at {cruise_alt:.0f}m AGL — commencing survey")

        for ring_idx, radius in enumerate(SURVEY_RADII):
            await self._emit("orbit_started", f"Ring {ring_idx+1}/{len(SURVEY_RADII)} — radius {radius:.0f}m — {ORBIT_POINTS} waypoints")
            orbit_readings = []
            for point_idx in range(ORBIT_POINTS):
                if not self._running:
                    return
                angle = (360.0 / ORBIT_POINTS) * point_idx
                pt_lat, pt_lon = _compute_orbit_point(center_lat, center_lon, radius, angle)

                await self._tool_handlers["fly_to"](
                    drone_id=self.drone_id, lat=pt_lat, lon=pt_lon, alt=cruise_alt
                )
                await self._emit("waypoint", f"Point {point_idx+1}/{ORBIT_POINTS} — {angle:.0f}° — ({pt_lat:.4f}, {pt_lon:.4f})")
                await self._wait_for_arrival(pt_lat, pt_lon)

                # Emit waypoint progress every other point to reduce noise
                if point_idx % 2 == 0:
                    await self._emit("at_waypoint", f"WP {point_idx + 1}/{ORBIT_POINTS}  ({pt_lat:.4f}, {pt_lon:.4f}) — scanning")

                reading = await self._tool_handlers["get_sensor_reading"](drone_id=self.drone_id)
                orbit_readings.append(reading)
                if reading.get("status") == "ok":
                    data = reading.get("data", {})
                    flags = ", ".join(data.get("hazard_flags", [])) or "none"
                    hit_summary = (
                        f"SENSOR HIT — thermal={'YES' if data.get('thermal_detected') else 'NO'}"
                        f"  survivor_prob={data.get('survivor_probability', 0):.0%}"
                        f"  wind={data.get('wind_speed', '?')}m/s"
                        f"  vis={data.get('visibility_m', '?')}m"
                        f"  flags=[{flags}]"
                    )
                    await self._emit("sensor_hit", hit_summary)

            hits = [r for r in orbit_readings if r.get("status") == "ok"]
            if hits:
                self.sensor_readings = hits
                await self._emit("ring_complete", f"Ring {ring_idx+1} done — {len(hits)}/{ORBIT_POINTS} sensor hits · classifying incident")
                await self._emit("llm_call", f"Calling model with tool_choice=report_classification · {len(hits)} sensor readings")
                await self._classify(center_lat, center_lon, radius, hits)
                return
            await self._emit("ring_clear", f"Ring {ring_idx+1} — no detections at {radius:.0f}m — expanding search")

    async def _classify(self, center_lat, center_lon, radius, sensor_hits) -> None:
        sensor_data = [h.get("data", h) for h in sensor_hits]
        observations = {
            "survey_center": {"lat": center_lat, "lon": center_lon},
            "confirmed_radius_m": radius,
            "operator_type_hint": self.type_hint,
            "sensor_readings": sensor_data,
        }
        messages = [
            {
                "role": "user",
                "content": (
                    f"Survey complete. The operator's type_hint was '{self.type_hint}' "
                    f"but classify from sensor data alone — confirm or revise:\n{observations}"
                ),
            }
        ]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self._system_prompt,
            messages=messages,
            tools=[REPORT_CLASSIFICATION_TOOL],
            tool_choice={"type": "tool", "name": "report_classification"},
        )

        classification_data = None
        for block in response.content:
            if block.type == "text" and block.text.strip():
                await self._emit("reasoning", block.text.strip())
            elif block.type == "tool_use" and block.name == "report_classification":
                kwargs_with_hash = {
                    **block.input,
                    "prompt_version_hash": self._prompt_version_hash,
                }
                await self._tool_handlers["report_classification"](**kwargs_with_hash)
                classification_data = block.input
                self.classification_reported = True
                c = block.input
                cls = c.get('classification', '?')
                conf = c.get('confidence', 0)
                confirmed = c.get('confirmed_hint', True)
                hint_note = '✓ confirmed hint' if confirmed else '✗ revised from hint'
                summary = (
                    f"CLASSIFIED: {cls.upper()}  "
                    f"{conf:.0%} confidence  "
                    f"r={c.get('area', {}).get('radius_m', '?')}m  "
                    f"{hint_note}"
                )
                await self._emit("classified", summary)
                logger.info("agent1_classified", classification=cls)

        if classification_data:
            await self._tool_handlers["fly_to"](
                drone_id=self.drone_id, lat=center_lat, lon=center_lon, alt=80.0
            )
            await self._emit("loitering", f"Loitering at ({center_lat:.4f}, {center_lon:.4f}) alt 80m — assessing situation")
            await self._decide(classification_data)
        """Second LLM call: decide whether to request specialist backup or maintain surveillance."""
        c = classification_data
        sensor_sum = c.get("sensor_summary", {})
        messages = [
            {
                "role": "user",
                "content": (
                    f"Classification: {c.get('classification')} "
                    f"(confidence {c.get('confidence', 0):.0%})\n"
                    f"Notes: {c.get('notes', 'none')}\n"
                    f"Sensor summary: thermal={sensor_sum.get('thermal_detected')}, "
                    f"survivor_probability={sensor_sum.get('survivor_probability', 0):.0%}, "
                    f"hazards={sensor_sum.get('hazard_flags', [])}, "
                    f"wind={sensor_sum.get('wind_speed', '?')}m/s, "
                    f"visibility={sensor_sum.get('visibility_m', '?')}m\n\n"
                    "Based on your assessment, decide: request specialist backup or maintain surveillance?"
                ),
            }
        ]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=self._system_prompt,
            messages=messages,
            tools=[REQUEST_BACKUP_TOOL, MAINTAIN_SURVEILLANCE_TOOL],
            tool_choice={"type": "any"},
        )

        for block in response.content:
            if block.type == "text" and block.text.strip():
                await self._emit("reasoning", block.text.strip())
            elif block.type == "tool_use":
                inp = block.input
                if block.name == "request_backup":
                    summary = (
                        f"REQUEST BACKUP — {inp.get('swarm_type', '?').replace('_', ' ').upper()} swarm"
                        f" — {inp.get('urgency', '?')} urgency"
                        f" — est. {inp.get('estimated_casualties', 0)} casualties"
                    )
                    await self._emit("decision", summary)
                    await self._emit("rationale", inp.get("rationale", ""))
                    result = await self._tool_handlers["request_backup"](**inp)
                    logger.info("agent1_requested_backup", swarm_type=inp.get("swarm_type"), urgency=inp.get("urgency"))
                elif block.name == "maintain_surveillance":
                    summary = (
                        f"MAINTAIN SURVEILLANCE"
                        f" — reassess in {inp.get('reassess_in_seconds', '?')}s"
                        f" — {inp.get('reason', '')}"
                    )
                    await self._emit("decision", summary)
                    result = await self._tool_handlers["maintain_surveillance"](**inp)
                    logger.info("agent1_maintain_surveillance", reason=inp.get("reason"))

    async def _wait_for_arrival(self, target_lat, target_lon, threshold_m=20.0) -> None:
        while self._running:
            telemetry = self.world_state.get_drone_telemetry(self.drone_id)
            if telemetry is None:
                await asyncio.sleep(0.5)
                continue
            dist = _haversine(telemetry.lat, telemetry.lon, target_lat, target_lon)
            if dist < threshold_m:
                return
            await asyncio.sleep(0.2)

    def stop(self) -> None:
        self._running = False
