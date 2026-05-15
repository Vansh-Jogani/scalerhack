"""ARIA Orchestrator — LangGraph state machine with SQLite checkpointer.

Graph: START → surveillance_node → swarm_node → advisory_node → END
Agent callbacks resolve asyncio Futures to bridge event-driven agents into LangGraph nodes.
State checkpointed to aria_checkpoints.db after each node.
"""

import asyncio
import time
from typing import Any, Optional, TypedDict

import structlog

from orchestrator.event_bus import EventBus

logger = structlog.get_logger()


class ARIAState(TypedDict):
    incident_id: str
    go_payload: dict
    agent1_report: Optional[dict]
    agent2_findings: Optional[dict]
    advisory: Optional[dict]
    error: Optional[str]


class ARIAOrchestrator:
    states = [
        "STANDBY",
        "SURVEILLANCE_ACTIVE",
        "SWARM_ACTIVE",
        "ADVISORY_ACTIVE",
        "MULTI_INCIDENT",
        "EMERGENCY",
    ]

    def __init__(
        self,
        world_state,
        sensor_overlay=None,
        model_a1: str = "claude-haiku-4-5-20251001",
        model_a2: str = "claude-haiku-4-5-20251001",
        model_a3: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.model_a1 = model_a1
        self.model_a2 = model_a2
        self.model_a3 = model_a3
        self.state = "STANDBY"
        self.active_incident: dict | None = None
        self.event_callback = None
        self.agent1_report: dict | None = None
        self.agent2_report: dict | None = None
        self._agent1_future: asyncio.Future | None = None
        self._agent2_future: asyncio.Future | None = None
        self.event_bus = EventBus()
        self.latest_briefing = None
        self._graph = None

    def set_event_callback(self, callback) -> None:
        self.event_callback = callback

    def setup_graph(self, checkpointer) -> None:
        """Compile LangGraph graph with SQLite checkpointer."""
        from langgraph.graph import StateGraph, START, END

        builder = StateGraph(ARIAState)
        builder.add_node("surveillance", self._surveillance_node)
        builder.add_node("swarm", self._swarm_node)
        builder.add_node("advisory", self._advisory_node)
        builder.add_edge(START, "surveillance")
        builder.add_edge("surveillance", "swarm")
        builder.add_edge("swarm", "advisory")
        builder.add_edge("advisory", END)
        self._graph = builder.compile(checkpointer=checkpointer)
        logger.info("langgraph_compiled")

    # ── Public API ────────────────────────────────────────────────────────────

    async def receive_go_signal(self, payload: dict) -> dict:
        """Process GO signal from operator. Returns stripped agent1 payload."""
        area = payload["area"]
        disaster_type = payload.get("disaster_type", "unknown")
        incident_id = f"INC-{int(time.time())}"

        self.active_incident = {
            "area": area,
            "disaster_type": disaster_type,
            "incident_id": incident_id,
        }
        self.agent1_report = None
        self.agent2_report = None
        self.latest_briefing = None

        if self.sensor_overlay:
            center = area["center"]
            radius_m = area.get("radius_m", 600.0)
            self.sensor_overlay.set_incident(
                center["lat"], center["lon"], radius_m, disaster_type
            )

        self.state = "SURVEILLANCE_ACTIVE"
        agent1_payload = {
            "action": "go",
            "coordinates": area["center"],
            "incident_id": incident_id,
        }
        logger.info("go_signal_processed", state=self.state, disaster_type=disaster_type, incident_id=incident_id)

        if self._graph:
            asyncio.create_task(self._run_graph(incident_id, agent1_payload))
        else:
            asyncio.create_task(self._run_incident_stack_fallback(agent1_payload))

        return agent1_payload

    def receive_agent1_report(self, report: dict) -> None:
        self.agent1_report = report
        logger.info("agent1_report_received", classification=report.get("classification"))
        if self._agent1_future and not self._agent1_future.done():
            self._agent1_future.set_result(report)
        asyncio.create_task(self._subscribe_and_publish_a1(report))

    def receive_agent2_report(self, report: dict) -> None:
        self.agent2_report = report
        logger.info("agent2_report_received", coverage=report.get("coverage_pct"))
        if self._agent2_future and not self._agent2_future.done():
            self._agent2_future.set_result(report)
        # Add zones/survivors to world_state for broadcast
        incident_id = (self.active_incident or {}).get("incident_id", "")
        for zone in report.get("zones_assessed", []):
            self.world_state.add_zone({
                "id": zone.get("zone_id", f"zone-{zone['lat']:.4f}-{zone['lon']:.4f}"),
                "lat": zone["lat"],
                "lon": zone["lon"],
                "radius_m": 100,
                "risk_level": zone.get("risk_level", "medium"),
                "label": zone.get("zone_id", ""),
                "incident_id": incident_id,
            })
        for idx, survivor in enumerate(report.get("survivor_detections", [])):
            sid = f"surv-{incident_id}-{idx}"
            self.world_state.add_survivor({
                "id": sid,
                "lat": survivor["lat"],
                "lon": survivor["lon"],
                "count": 1,
                "probability": survivor.get("confidence", 0.5),
                "incident_id": incident_id,
            })
        for hazard in report.get("hazard_map", []):
            self.world_state.add_hazard({**hazard, "incident_id": incident_id})
        asyncio.create_task(self._publish_agent2_findings(report))

    def get_incident_context(self) -> dict | None:
        return self.active_incident

    async def trigger_world_event(self, event: dict) -> None:
        await self._emit("agent_stream", {"agent_id": "world", "event": "world_event", "content": event})
        await self.event_bus.publish("world_event_fired", event)

    # ── LangGraph nodes ───────────────────────────────────────────────────────

    async def _surveillance_node(self, state: ARIAState) -> dict:
        from agents.agent1_surveillance import SurveillanceAgent

        loop = asyncio.get_event_loop()
        self._agent1_future = loop.create_future()

        agent1 = SurveillanceAgent(
            agent_id=f"agent-1-{state['incident_id']}",
            model=self.model_a1,
            world_state=self.world_state,
            sensor_overlay=self.sensor_overlay,
            orchestrator=self,
            drone_id="drone-001",
            stream_callback=self.event_callback,
        )
        await self._emit("agent_stream", {"agent_id": "agent-1", "event": "started", "content": state["go_payload"]})
        asyncio.create_task(agent1.receive_go(state["go_payload"]))
        self.state = "SURVEILLANCE_ACTIVE"

        try:
            report = await asyncio.wait_for(self._agent1_future, timeout=300.0)
        except asyncio.TimeoutError:
            logger.error("agent1_timeout")
            return {"error": "agent1 timeout", "agent1_report": None}
        finally:
            self._agent1_future = None

        return {"agent1_report": report if isinstance(report, dict) else dict(report)}

    async def _swarm_node(self, state: ARIAState) -> dict:
        from agents.agent2_specialist import SpecialistAgent

        a1_report = state.get("agent1_report") or {}
        if not a1_report:
            logger.warning("swarm_node_no_agent1_report")
            return {"agent2_findings": {}}

        loop = asyncio.get_event_loop()
        self._agent2_future = loop.create_future()

        classification = a1_report.get("classification", "fire")
        agent2 = SpecialistAgent(
            agent_id=f"agent-2-{state['incident_id']}",
            model=self.model_a2,
            world_state=self.world_state,
            sensor_overlay=self.sensor_overlay,
            orchestrator=self,
            classification=classification,
            incident_id=state["incident_id"],
            stream_callback=self.event_callback,
        )
        await self._emit("agent_stream", {
            "agent_id": "agent-2", "event": "started",
            "content": f"Deploying {classification} swarm",
        })
        asyncio.create_task(agent2.run(a1_report))
        self.state = "SWARM_ACTIVE"

        try:
            findings = await asyncio.wait_for(self._agent2_future, timeout=300.0)
        except asyncio.TimeoutError:
            logger.error("agent2_timeout")
            return {"agent2_findings": {}}
        finally:
            self._agent2_future = None

        return {"agent2_findings": findings if isinstance(findings, dict) else dict(findings)}

    async def _advisory_node(self, state: ARIAState) -> dict:
        from agents.agent3_advisory import AdvisoryAgent
        from agents.messages import IncidentBriefing

        self.state = "ADVISORY_ACTIVE"
        briefing = IncidentBriefing.from_dicts(
            incident_id=state["incident_id"],
            a1_data=state.get("agent1_report") or {},
            a2_data=state.get("agent2_findings") or {},
            previous_advisory=None,
        )
        self.latest_briefing = briefing

        agent3 = AdvisoryAgent(model=self.model_a3, orchestrator=self)
        await self._emit("agent_stream", {"agent_id": "agent-3", "event": "started", "content": "Generating advisory"})
        advisory = await agent3.on_trigger(briefing)
        await self._emit("advisory", advisory)
        await self._emit("agent_stream", {
            "agent_id": "agent-3", "event": "advisory_issued",
            "content": advisory.get("situation_summary", ""),
        })
        return {"advisory": advisory}

    # ── EventBus integration ──────────────────────────────────────────────────

    async def _subscribe_and_publish_a1(self, report: dict) -> None:
        for trigger in [
            "agent_1_report_received",
            "agent_2_findings_updated",
            "world_event_fired",
            "operator_query",
            "heartbeat_check",
        ]:
            self.event_bus.subscribe(trigger, self._handle_agent3_trigger)
        await self.event_bus.publish("agent_1_report_received", report)
        self.event_bus.start_heartbeat(
            lambda p: asyncio.ensure_future(self.event_bus.publish("heartbeat_check", p))
        )

    async def _publish_agent2_findings(self, report: dict) -> None:
        incident_id = (self.active_incident or {}).get("incident_id", "")
        from agents.messages import IncidentBriefing
        self.latest_briefing = IncidentBriefing.from_dicts(
            incident_id=incident_id,
            a1_data=self.agent1_report or {},
            a2_data=report,
        )
        await self.event_bus.publish("agent_2_findings_updated", report)

    async def _handle_agent3_trigger(self, payload: Any) -> None:
        """Single handler for all EventBus events — re-triggers Agent 3."""
        from agents.agent3_advisory import AdvisoryAgent
        from agents.messages import IncidentBriefing
        if not self.agent1_report:
            return
        briefing = self.latest_briefing
        if briefing is None:
            incident_id = (self.active_incident or {}).get("incident_id", "")
            briefing = IncidentBriefing.from_dicts(
                incident_id=incident_id,
                a1_data=self.agent1_report,
                a2_data=self.agent2_report or {},
            )
        agent3 = AdvisoryAgent(model=self.model_a3, orchestrator=self)
        advisory = await agent3.on_trigger(briefing)
        await self._emit("advisory", advisory)
        await self._emit("agent_stream", {
            "agent_id": "agent-3", "event": "advisory_updated",
            "content": advisory.get("situation_summary", ""),
        })

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run_graph(self, incident_id: str, agent1_payload: dict) -> None:
        try:
            await self._graph.ainvoke(
                {
                    "incident_id": incident_id,
                    "go_payload": agent1_payload,
                    "agent1_report": None,
                    "agent2_findings": None,
                    "advisory": None,
                    "error": None,
                },
                config={"configurable": {"thread_id": incident_id}},
            )
        except Exception as e:
            logger.error("graph_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "error", "content": str(e)})

    async def _run_incident_stack_fallback(self, agent1_payload: dict) -> None:
        """Fallback sequential pipeline when LangGraph is not available."""
        from agents.agent1_surveillance import SurveillanceAgent
        from agents.agent2_specialist import SpecialistAgent
        from agents.agent3_advisory import AdvisoryAgent
        from agents.messages import IncidentBriefing

        incident_id = (self.active_incident or {}).get("incident_id", "fallback")
        try:
            agent1 = SurveillanceAgent(
                agent_id="agent-1", model=self.model_a1,
                world_state=self.world_state, sensor_overlay=self.sensor_overlay,
                orchestrator=self, drone_id="drone-001", stream_callback=self.event_callback,
            )
            await self._emit("agent_stream", {"agent_id": "agent-1", "event": "started", "content": agent1_payload})
            await agent1.receive_go(agent1_payload)
            self.state = "SWARM_ACTIVE"

            classification = (self.agent1_report or {}).get("classification", "fire")
            agent2 = SpecialistAgent(
                agent_id="agent-2", model=self.model_a2,
                world_state=self.world_state, sensor_overlay=self.sensor_overlay,
                orchestrator=self, classification=classification, incident_id=incident_id,
                stream_callback=self.event_callback,
            )
            await self._emit("agent_stream", {"agent_id": "agent-2", "event": "started", "content": f"Deploying {classification} swarm"})
            await agent2.run(self.agent1_report or {})
            self.state = "ADVISORY_ACTIVE"

            briefing = IncidentBriefing.from_dicts(
                incident_id=incident_id,
                a1_data=self.agent1_report or {},
                a2_data=self.agent2_report or {},
            )
            agent3 = AdvisoryAgent(model=self.model_a3, orchestrator=self)
            await self._emit("agent_stream", {"agent_id": "agent-3", "event": "started", "content": "Generating advisory"})
            advisory = await agent3.on_trigger(briefing)
            await self._emit("advisory", advisory)

        except Exception as e:
            logger.error("incident_stack_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "error", "content": str(e)})

    async def _emit(self, event_type: str, data: dict) -> None:
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.warning("emit_error", event_type=event_type, error=str(e))
