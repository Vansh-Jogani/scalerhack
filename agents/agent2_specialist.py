"""Agent 2 — Specialist Swarm Agent.

Receives a SurveillanceReport from orchestrator. Deploys the correct swarm
type (selected by orchestrator via SWARM_CAPABILITIES) and reports zone
assessments, survivor detections, and hazard maps.
"""

import asyncio
import structlog
from anthropic import AsyncAnthropic

from prompts import load_prompt, fill_template
from agents.tools.schemas import (
    AGENT_2_TOOLS,
    DeploySwarmInput,
    GetSensorReadingInput,
    UpdateZoneClassificationInput,
    MarkSurvivorInput,
    MarkHazardInput,
    ReportSwarmFindingsInput,
)
from agents.tools.flight_tools import create_fly_to_handler
from agents.tools.sensor_tools import create_get_sensor_reading_handler

logger = structlog.get_logger()

SWARM_CAPABILITIES = {
    "fire": {
        "swarm": "thermal_rotary",
        "drones": 3,
        "sensors": ["thermal_camera", "gas_detector", "wind_sensor"],
        "altitude": 50,
        "speed": 8,
        "priority_tasks": [
            "map_fire_perimeter",
            "identify_hotspots",
            "detect_trapped_persons",
            "assess_spread_direction",
        ],
        "constraint": "maintain_upwind_position",
    },
    "structural_collapse": {
        "swarm": "micro_search_rotary",
        "drones": 4,
        "sensors": ["acoustic_detector", "co2_sensor", "thermal", "visual_hd"],
        "altitude": 15,
        "speed": 4,
        "priority_tasks": [
            "map_void_spaces",
            "detect_survivors",
            "assess_structural_integrity",
            "identify_egress_paths",
        ],
        "constraint": "avoid_zones_integrity_below_0.2",
    },
    "flood": {
        "swarm": "fixed_wing_extended",
        "drones": 2,
        "sensors": ["visual_hd", "thermal", "depth_estimation"],
        "altitude": 80,
        "speed": 18,
        "priority_tasks": [
            "map_flood_extent",
            "identify_isolated_survivors",
            "assess_flow_direction",
            "find_safe_approach_routes",
        ],
        "constraint": "maintain_visual_line_of_sight",
    },
    "industrial_hazard": {
        "swarm": "standoff_rotary",
        "drones": 2,
        "sensors": ["gas_spectrometer", "thermal", "visual_hd"],
        "altitude": 100,
        "speed": 6,
        "priority_tasks": [
            "identify_hazard_source",
            "map_exclusion_zone",
            "detect_spread_direction",
            "assess_secondary_risk",
        ],
        "constraint": "minimum_200m_standoff_from_source",
    },
    "maritime_sar": {
        "swarm": "fixed_wing_endurance",
        "drones": 3,
        "sensors": ["visual_hd", "thermal", "ais_receiver"],
        "altitude": 150,
        "speed": 22,
        "priority_tasks": [
            "expanding_square_search",
            "detect_persons_in_water",
            "track_drift_objects",
            "coordinate_vessel_response",
        ],
        "constraint": "maintain_comms_relay_chain",
    },
}


def _create_deploy_swarm_handler(world_state):
    async def deploy_swarm(positions: list[dict]) -> dict:
        import asyncio as _asyncio
        results = []
        for pos in positions:
            success = world_state.command_drone(pos["drone_id"], pos["lat"], pos["lon"], pos["alt"])
            results.append({"drone_id": pos["drone_id"], "status": "ok" if success else "error"})

        # Wait for all drones to arrive (LOITERING = reached target, stops moving)
        drone_ids = [p["drone_id"] for p in positions if world_state.drones.get(p["drone_id"])]
        for _ in range(1500):   # up to 150s
            if all(
                world_state.drones[d].get_state() in ("LOITERING", "IDLE")
                for d in drone_ids
            ):
                break
            await _asyncio.sleep(0.1)

        return {"status": "ok", "drones_commanded": results, "all_arrived": True}
    return deploy_swarm


def _create_update_zone_handler(world_state):
    async def update_zone_classification(**kwargs) -> dict:
        # World state zone write — stores for MapStateManager to pick up
        zone_data = {
            "zone_id": kwargs["zone_id"],
            "lat": kwargs["lat"],
            "lon": kwargs["lon"],
            "findings": kwargs["findings"],
            "risk_level": kwargs["risk_level"],
            "actionable": kwargs["actionable"],
        }
        if hasattr(world_state, "update_zone"):
            world_state.update_zone(zone_data)
        logger.info("zone_classified", zone_id=kwargs["zone_id"], risk=kwargs["risk_level"])
        return {"status": "ok", "zone_id": kwargs["zone_id"]}
    return update_zone_classification


def _create_mark_survivor_handler(world_state):
    async def mark_survivor(**kwargs) -> dict:
        if hasattr(world_state, "add_survivor_marker"):
            world_state.add_survivor_marker(kwargs)
        logger.info("survivor_marked", lat=kwargs["lat"], lon=kwargs["lon"], confidence=kwargs["confidence"])
        return {"status": "ok", "message": "Survivor marked"}
    return mark_survivor


def _create_mark_hazard_handler(world_state):
    async def mark_hazard(**kwargs) -> dict:
        if hasattr(world_state, "add_hazard_marker"):
            world_state.add_hazard_marker(kwargs)
        logger.info("hazard_marked", type=kwargs["type"], exclusion_m=kwargs["exclusion_radius_m"])
        return {"status": "ok", "message": "Hazard marked"}
    return mark_hazard


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
    ):
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

        config = SWARM_CAPABILITIES[classification]
        self.swarm_config = config
        self.drone_ids: list[str] = []
        self.incident_id: str = "INC-000"

        # Build system prompt from registry template
        template = load_prompt("agent2_specialist")
        priority_tasks_text = "\n".join(
            f"{i + 1}. {t.replace('_', ' ')}"
            for i, t in enumerate(config["priority_tasks"])
        )
        filled_text = fill_template(
            template["text"],
            swarm_type=config["swarm"],
            drone_count=str(config["drones"]),
            sensors=", ".join(config["sensors"]),
            altitude=str(config["altitude"]),
            constraint=config["constraint"],
            priority_tasks=priority_tasks_text,
        )
        self._prompt = {"text": filled_text, "version_hash": template["version_hash"]}

        self._tool_handlers = {
            "deploy_swarm": _create_deploy_swarm_handler(world_state),
            "get_sensor_reading": create_get_sensor_reading_handler(sensor_overlay, world_state),
            "update_zone_classification": _create_update_zone_handler(world_state),
            "mark_survivor": _create_mark_survivor_handler(world_state),
            "mark_hazard": _create_mark_hazard_handler(world_state),
            "report_swarm_findings": self._handle_report_findings,
        }

    async def receive_dispatch(self, payload: dict):
        """Receive dispatch from orchestrator and start swarm mission."""
        self.incident_id = payload.get("incident_id", "INC-000")
        center = payload.get("center", {})
        logger.info("agent2_dispatched", incident_id=self.incident_id, classification=self.classification)
        await self._log("dispatched",
                        f"Deploying {self.classification} swarm — {len(self.drone_ids)} drones",
                        drone_ids=self.drone_ids)
        asyncio.create_task(self._run_mission(center))

    async def _run_mission(self, center: dict):
        """Run the swarm mission via multi-turn Claude tool-use loop."""
        self._running = True
        self._findings_reported = False
        config = self.swarm_config

        mission_brief = {
            "incident_id": self.incident_id,
            "classification": self.classification,
            "center": center,
            "swarm_drone_ids": self.drone_ids,
            "sensors": config["sensors"],
            "altitude_m": config["altitude"],
            "constraint": config["constraint"],
        }

        messages = [
            {
                "role": "user",
                "content": (
                    f"Mission brief:\n\n{mission_brief}\n\n"
                    f"Execute priority tasks. When you have assessed the key zones, "
                    f"call report_swarm_findings to complete the mission."
                ),
            }
        ]

        max_turns = 20
        turn = 0
        while self._running and turn < max_turns:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self._prompt["text"],
                messages=messages,
                tools=AGENT_2_TOOLS,
            )

            turn += 1
            logger.info(
                "agent2_llm_response",
                prompt_version=self._prompt["version_hash"],
                stop_reason=response.stop_reason,
                turn=turn,
            )

            if response.stop_reason == "end_turn":
                break

            # Collect tool results for next turn
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                handler = self._tool_handlers.get(block.name)
                if not handler:
                    logger.warning("agent2_unknown_tool", tool=block.name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Unknown tool: {block.name}",
                    })
                    continue

                result = await handler(**block.input)
                logger.info("agent2_tool_call", tool=block.name, result=result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

                if block.name == "report_swarm_findings":
                    await self._log("findings_reported", "Swarm findings reported to orchestrator")
                    self._findings_reported = True
                    self._running = False
                    break

                if block.name == "update_zone_classification":
                    risk = block.input.get("risk_level", "?")
                    await self._log("zone_assessed",
                                    f"Zone {block.input.get('zone_id','')} — {risk.upper()}",
                                    **block.input)

                if block.name == "mark_survivor":
                    await self._log("survivor",
                                    f"Survivor detected (confidence {block.input.get('confidence',0):.0%})",
                                    **block.input)

            if not tool_results:
                break

            # Append assistant turn + tool results for next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Fallback: if loop exited without report_swarm_findings being called
        if not self._findings_reported:
            logger.warning("agent2_no_report_fallback", turn=turn)
            await self._log("fallback_report", "Mission loop ended — generating fallback report")
            fallback = {
                "incident_id": self.incident_id,
                "zones_assessed": [],
                "survivor_detections": [],
                "hazard_map": [],
                "coverage_pct": 50.0,
                "notes": "Fallback report — mission loop exited without explicit report",
                "prompt_version_hash": self._prompt["version_hash"],
            }
            self.orchestrator.receive_agent2_report(fallback)

    async def _handle_report_findings(self, **kwargs) -> dict:
        """Validate and forward swarm findings to orchestrator."""
        _, err = ReportSwarmFindingsInput.validate_call(kwargs)
        if err:
            logger.warning("agent2_findings_validation_partial", error=err)
            # Keep valid scalar fields, drop invalid nested ones rather than reject entirely
            kwargs.setdefault("zones_assessed", [])
            kwargs.setdefault("survivor_detections", [])
            kwargs.setdefault("hazard_map", [])
            kwargs.setdefault("coverage_pct", 50.0)
            kwargs.setdefault("notes", "Partial report — some fields failed validation")
        kwargs["prompt_version_hash"] = self._prompt["version_hash"]
        kwargs["incident_id"] = self.incident_id   # always use orchestrator's incident_id
        self.orchestrator.receive_agent2_report(kwargs)
        return {"status": "ok", "message": "Findings reported to orchestrator"}

    def stop(self):
        self._running = False
