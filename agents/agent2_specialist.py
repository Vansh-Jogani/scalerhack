"""Agent 2 — Specialist Swarm Agent.

Inherits BaseAgent. Deploys specialist swarm based on swarm_config
SELECTED BY CLASSIFIER — Agent 2 does NOT choose its swarm type.

Per SPEC.md: "Swarm selection is locked to a decision table in code.
Agent reasons within it — does not choose the swarm type."
"""

import math
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

Incident classification from surveillance: {classification}
Swarm type: {swarm_type}
Sensors available: {sensors}
Operating altitude: {altitude}m AGL
Operating speed: {speed} m/s

HARD CONSTRAINT (you MUST follow this at all times): {constraint}

Your priority tasks (execute in this order):
{priority_tasks}

Your mission:
1. Deploy swarm drones to cover the incident area
2. Execute priority tasks in order using sensor readings
3. Annotate zones with classifications and confidence levels
4. Mark survivor locations when detected
5. Report consolidated findings when assessment is complete

Your drones: {drone_ids}

Available tools: fly_to, loiter_over, get_sensor_reading,
                 zone_annotate, survivor_marker, report_findings

Rules:
- Execute priority tasks in the specified order
- Always operate within the hard constraint above
- Report all zones assessed with risk levels
- Mark every survivor detection with location and confidence
"""


class SpecialistAgent(BaseAgent):
    """Agent 2: Specialist swarm — deploys configured swarm, assesses zones.

    Receives swarm_config from classifier — does NOT choose it.
    Inherits BaseAgent OODA-R loop.
    """

    def __init__(
        self,
        agent_id: str,
        model: str,
        world_state,
        sensor_overlay,
        orchestrator,
        swarm_config: dict,
        classification: str,
        stream_callback=None,
    ):
        self.swarm_config = swarm_config
        self.classification = classification
        self.orchestrator = orchestrator
        self.spawned_drone_ids: list[str] = []

        # Build tool list (6 tools)
        tools = [
            FLY_TO_TOOL,
            LOITER_OVER_TOOL,
            GET_SENSOR_READING_TOOL,
            ZONE_ANNOTATE_TOOL,
            SURVIVOR_MARKER_TOOL,
            REPORT_FINDINGS_TOOL,
        ]

        # Build tool handlers
        tool_handlers = {
            "fly_to": create_fly_to_handler(world_state),
            "loiter_over": create_loiter_over_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "zone_annotate": create_zone_annotate_handler(),
            "survivor_marker": create_survivor_marker_handler(),
            "report_findings": create_report_findings_handler(orchestrator),
        }

        # Format system prompt with swarm config details
        system_prompt = AGENT_2_SYSTEM_PROMPT_TEMPLATE.format(
            swarm_type=swarm_config["swarm"],
            drone_count=swarm_config["drones"],
            classification=classification,
            sensors=", ".join(swarm_config["sensors"]),
            altitude=swarm_config["altitude"],
            speed=swarm_config["speed"],
            constraint=swarm_config["constraint"],
            priority_tasks="\n".join(f"  {i+1}. {t}" for i, t in enumerate(swarm_config["priority_tasks"])),
            drone_ids="(will be assigned after spawn)",
        )

        super().__init__(
            agent_id=agent_id,
            system_prompt=system_prompt,
            model=model,
            world_state=world_state,
            sensor_overlay=sensor_overlay,
            drone_ids=[],  # populated after spawning
            tools=tools,
            tool_handlers=tool_handlers,
            interval=2.0,
            stream_callback=stream_callback,
        )

    async def observe(self) -> dict:
        """Extend base observe with swarm-specific context."""
        obs = await super().observe()
        obs["swarm_context"] = {
            "classification": self.classification,
            "swarm_type": self.swarm_config["swarm"],
            "drone_ids": self.drone_ids,
            "priority_tasks": self.swarm_config["priority_tasks"],
            "constraint": self.swarm_config["constraint"],
        }
        return obs

    async def run_mission(self, agent1_report: dict) -> None:
        """Deploy swarm drones, then run the OODA-R loop.

        Spawns the number of drones specified in swarm_config,
        then starts the BaseAgent loop with an initial message.
        """
        # Determine drone type from swarm config
        swarm_name = self.swarm_config["swarm"]
        if "micro" in swarm_name:
            drone_type = "micro_rotary"
        elif "fixed_wing" in swarm_name or "endurance" in swarm_name:
            drone_type = "fixed_wing"
        else:
            drone_type = "rotary"

        # Get center coordinates from agent1 report
        center_lat = agent1_report.get("center_lat",
            agent1_report.get("area", {}).get("center", {}).get("lat", 17.385))
        center_lon = agent1_report.get("center_lon",
            agent1_report.get("area", {}).get("center", {}).get("lon", 78.4867))

        # Spawn swarm drones
        num_drones = self.swarm_config["drones"]
        for i in range(num_drones):
            drone_id = f"swarm-{self.agent_id}-{i}"
            # Spread drones slightly around center
            offset = i * 0.0005
            self.world_state.add_drone(drone_id, drone_type, center_lat + offset, center_lon)
            self.drone_ids.append(drone_id)
            self.spawned_drone_ids.append(drone_id)
            logger.info("swarm_drone_spawned", drone_id=drone_id, type=drone_type)

        # Update system prompt with actual drone IDs
        self.system_prompt = self.system_prompt.replace(
            "(will be assigned after spawn)",
            ", ".join(self.drone_ids),
        )

        if self.stream_callback:
            await self._emit("swarm_deployed", {
                "drones": self.drone_ids,
                "type": drone_type,
                "count": num_drones,
            })

        # Build initial message with agent1 report and mission parameters
        initial_msg = (
            f"Agent 1 surveillance report: {agent1_report}\n\n"
            f"You have {num_drones} {drone_type} drones deployed: {', '.join(self.drone_ids)}\n"
            f"Center coordinates: lat={center_lat}, lon={center_lon}\n"
            f"Operating altitude: {self.swarm_config['altitude']}m\n"
            f"Begin specialist assessment. Execute priority tasks in order."
        )

        await self.run(initial_message=initial_msg)
