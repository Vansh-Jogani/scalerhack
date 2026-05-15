"""ARIA Orchestrator — deterministic state machine.

Receives GO signal from operator, holds full context (area + disaster_type),
forwards only coordinates to Agent 1, then chains Agent 2 and Agent 3.
"""

import asyncio
import structlog

logger = structlog.get_logger()


class ARIAOrchestrator:
    states = [
        "STANDBY",
        "SURVEILLANCE_ACTIVE",
        "SWARM_ACTIVE",
        "ADVISORY_ACTIVE",
        "MULTI_INCIDENT",
        "EMERGENCY",
    ]

    def __init__(self, world_state, sensor_overlay=None,
                 model: str = "claude-haiku-4-5-20251001",
                 agent3_endpoint: str = "http://localhost:11434/api/chat",
                 agent3_model: str = "llama3.1:8b"):
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.model = model
        self.agent3_endpoint = agent3_endpoint
        self.agent3_model = agent3_model
        self.state = "STANDBY"
        self.active_incident = None
        self.event_callback = None
        self.agent1_report = None
        self.agent2_report = None

    def set_event_callback(self, callback) -> None:
        """Register async callback for broadcasting events to connected clients."""
        self.event_callback = callback

    async def receive_go_signal(self, payload: dict) -> dict:
        """Process GO signal from operator.

        Stores full area context. Fires off the incident stack as a background task.
        Returns stripped payload for Agent 1 immediately (used in WebSocket ack).
        """
        area = payload["area"]
        disaster_type = payload.get("disaster_type", "unknown")

        self.active_incident = {
            "area": area,
            "disaster_type": disaster_type,
        }
        self.agent1_report = None
        self.agent2_report = None

        if self.sensor_overlay and "boundary_polygon" in area:
            self.sensor_overlay.set_incident(area["boundary_polygon"], disaster_type)

        self.state = "SURVEILLANCE_ACTIVE"

        agent1_payload = {
            "action": "go",
            "coordinates": area["center"],
        }

        logger.info(
            "go_signal_processed",
            state=self.state,
            disaster_type=disaster_type,
            center=area["center"],
        )

        asyncio.create_task(self._run_incident_stack(agent1_payload))
        return agent1_payload

    async def _run_incident_stack(self, agent1_payload: dict) -> None:
        """Run the full Agent 1 → Agent 2 → Agent 3 pipeline."""
        from agents.agent1_surveillance import SurveillanceAgent
        from agents.agent2_specialist import SpecialistAgent
        from agents.agent3_advisory import AdvisoryAgent

        try:
            # --- Agent 1 ---
            agent1 = SurveillanceAgent(
                agent_id="agent-1",
                model=self.model,
                world_state=self.world_state,
                sensor_overlay=self.sensor_overlay,
                orchestrator=self,
                drone_id="drone-001",
                stream_callback=self.event_callback,
            )
            await self._emit("agent_stream", {
                "agent_id": "agent-1", "event": "started", "content": agent1_payload,
            })
            await agent1.receive_go(agent1_payload)
            self.state = "SWARM_ACTIVE"

            # --- Agent 2 ---
            classification = (self.agent1_report or {}).get("classification", "fire")
            agent2 = SpecialistAgent(
                agent_id="agent-2",
                model=self.model,
                world_state=self.world_state,
                sensor_overlay=self.sensor_overlay,
                orchestrator=self,
                classification=classification,
                stream_callback=self.event_callback,
            )
            await self._emit("agent_stream", {
                "agent_id": "agent-2", "event": "started",
                "content": f"Deploying {classification} swarm",
            })
            await agent2.run(self.agent1_report or {})
            self.state = "ADVISORY_ACTIVE"

            # --- Agent 3 ---
            agent3 = AdvisoryAgent(
                agent_id="agent-3",
                endpoint=self.agent3_endpoint,
                model=self.agent3_model,
                orchestrator=self,
            )
            await self._emit("agent_stream", {
                "agent_id": "agent-3", "event": "started", "content": "Generating advisory",
            })
            advisory = await agent3.on_trigger(
                self.agent1_report or {},
                self.agent2_report or {},
            )
            await self._emit("advisory", advisory)
            await self._emit("agent_stream", {
                "agent_id": "agent-3", "event": "advisory_issued",
                "content": advisory.get("situation_summary", ""),
            })

        except Exception as e:
            logger.error("incident_stack_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {
                "agent_id": "orchestrator", "event": "error", "content": str(e),
            })

    async def trigger_world_event(self, event: dict) -> None:
        """Called when a world event fires (e.g. fire growth). Re-triggers Agent 3."""
        from agents.agent3_advisory import AdvisoryAgent

        await self._emit("agent_stream", {
            "agent_id": "world", "event": "world_event", "content": event,
        })

        if self.agent1_report:
            agent3 = AdvisoryAgent(
                agent_id="agent-3",
                endpoint=self.agent3_endpoint,
                model=self.agent3_model,
                orchestrator=self,
            )
            advisory = await agent3.on_trigger(
                self.agent1_report,
                self.agent2_report or {},
            )
            await self._emit("advisory", advisory)

    def get_incident_context(self) -> dict | None:
        """Return full incident context (used by sensor overlay, not agents)."""
        return self.active_incident

    def receive_agent1_report(self, report: dict) -> None:
        """Receive classification report from Agent 1."""
        self.agent1_report = report
        logger.info("agent1_report_received",
                    classification=report.get("classification"),
                    confidence=report.get("confidence"))

    def receive_agent2_report(self, report: dict) -> None:
        """Receive findings report from Agent 2."""
        self.agent2_report = report
        logger.info("agent2_report_received",
                    incident_id=report.get("incident_id"),
                    coverage=report.get("coverage_pct"))

    async def _emit(self, event_type: str, data: dict) -> None:
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.warning("emit_error", event_type=event_type, error=str(e))
