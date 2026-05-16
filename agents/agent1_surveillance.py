"""Agent 1 — Surveillance Agent.

Inherits BaseAgent. Uses the OODA-R loop to fly to incident coordinates,
survey the area, collect sensor data, classify the incident, and report
to the orchestrator.

System prompt is EXACTLY from SPEC.md AGENT_1_SYSTEM_PROMPT.
The LLM drives the survey — it decides tool call sequences.
"""

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
    REPORT_CLASSIFICATION_TOOL,
    REQUEST_DETAILED_PASS_TOOL,
    create_report_classification_handler,
    create_request_detailed_pass_handler,
)

logger = structlog.get_logger()

# Verbatim from SPEC.md — do not modify
AGENT_1_SYSTEM_PROMPT = """You are ARIA Surveillance Agent. You control fixed-wing reconnaissance drones.

You receive: Go signal with approximate coordinates
You know: Markers represent confirmed or probable incidents.
          Marker types: fire, structural_collapse, flood, industrial_hazard, maritime_sar

Your mission:
1. Fly to provided coordinates
2. When you overfly a marker, you receive sensor data
3. Classify the incident from sensor data + marker type
4. Establish loiter pattern over the incident area
5. Report classification and affected area to orchestrator

Your drones:
- Speed: 18 m/s cruise, 80m loiter radius
- Altitude: 120m AGL for survey, 60m for detailed pass
- You control 1-2 aircraft depending on area size

Rules:
- Complete one full orbit before reporting classification
- Always report confidence level with classification
- Flag if marker area has grown since initial flyover
- Never descend below 60m AGL

Available tools: fly_to, loiter_over, get_sensor_reading,
                 report_classification, request_detailed_pass
"""


class SurveillanceAgent(BaseAgent):
    """Agent 1: Surveillance — flies to incident, classifies, reports.

    Inherits BaseAgent OODA-R loop. The LLM decides the survey strategy
    via tool calls — we do NOT hardcode flight patterns.
    """

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
        # Build tool list (5 tools per SPEC.md)
        tools = [
            FLY_TO_TOOL,
            LOITER_OVER_TOOL,
            GET_SENSOR_READING_TOOL,
            REPORT_CLASSIFICATION_TOOL,
            REQUEST_DETAILED_PASS_TOOL,
        ]

        # Build tool handlers
        tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "loiter_over": create_loiter_over_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "report_classification": create_report_classification_handler(
                orchestrator,
                stream_callback=stream_callback,
                agent_id=agent_id,
            ),
            "request_detailed_pass": create_request_detailed_pass_handler(world_state, drone_id),
        }

        super().__init__(
            agent_id=agent_id,
            system_prompt=AGENT_1_SYSTEM_PROMPT,
            model=model,
            world_state=world_state,
            sensor_overlay=sensor_overlay,
            drone_ids=[drone_id],
            tools=tools,
            tool_handlers=tool_handlers,
            interval=2.0,
            stream_callback=stream_callback,
        )

        self.orchestrator = orchestrator
        self.drone_id = drone_id
        self.target_coords = None

    async def observe(self) -> dict:
        """Extend base observe with mission-specific context."""
        obs = await super().observe()
        obs["mission"] = {
            "target_coordinates": self.target_coords,
            "drone_id": self.drone_id,
            "agent_id": self.agent_id,
        }
        return obs

    async def receive_go(self, payload: dict) -> None:
        """Receive GO signal (coordinates only) and start the OODA-R loop.

        The initial message tells the LLM about the GO signal and target.
        The LLM then drives the survey via tool calls.
        """
        self.target_coords = payload.get("coordinates", {})
        lat = self.target_coords.get("lat", 0)
        lon = self.target_coords.get("lon", 0)

        initial_msg = (
            f"GO signal received. Target coordinates: lat={lat}, lon={lon}. "
            f"Your drone is {self.drone_id}. "
            f"Begin surveillance mission: fly to target, survey the area, "
            f"collect sensor readings, classify the incident, and report."
        )

        logger.info("agent1_go_received", coords=self.target_coords, drone=self.drone_id)
        await self.run(initial_message=initial_msg)

        # Emit completed event after the OODA-R loop finishes
        report = self.orchestrator.agent1_report or {}
        await self._emit("completed", {
            "classification": report.get("classification", "unknown"),
            "confidence": report.get("confidence", 0.0),
        })
