"""ARIA Orchestrator — LangGraph state machine with SQLite checkpointer.

Each incident runs as a LangGraph graph:
  surveillance_node → swarm_node → advisory_node

State is checkpointed to SQLite after every node, enabling crash recovery.
Agents run as asyncio tasks; their callbacks resolve asyncio Futures that
the LangGraph nodes await — bridging the event-driven agent API with the
LangGraph sequential-node model.
"""

import asyncio
import json
import time
import structlog

from typing import Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from pydantic import ValidationError

from agents.messages import SurveillanceReport, SwarmFindings, IncidentBriefing
from agents.agent3_advisory import AdvisoryAgent
from orchestrator.event_bus import EventBus

logger = structlog.get_logger()

# How many swarm drones per classification
_SWARM_COUNTS = {
    "fire": 3,
    "structural_collapse": 4,
    "flood": 2,
    "industrial_hazard": 2,
    "maritime_sar": 3,
}
_SWARM_TYPES = {
    "fire": "rotary",
    "structural_collapse": "micro_rotary",
    "flood": "fixed_wing",
    "industrial_hazard": "rotary",
    "maritime_sar": "fixed_wing",
}


class ARIAState(TypedDict):
    """Persisted state for one incident run."""
    orchestrator_state: str
    incident_id: str
    area: dict
    disaster_type: str
    # JSON-serialised typed models — stored as strings so SQLite can persist them
    surveillance_report_json: Optional[str]
    swarm_findings_json: Optional[str]
    latest_advisory_json: Optional[str]


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
        agent1_model: str = "claude-sonnet-4-20250514",
        agent2_model: str = "claude-sonnet-4-20250514",
        agent3_model: str = "claude-sonnet-4-20250514",
    ):
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self._agent1_model = agent1_model
        self._agent2_model = agent2_model
        self._agent3_model = agent3_model

        # In-memory state (LangGraph state is the durable copy)
        self.state = "STANDBY"
        self.active_incident: dict | None = None

        # Typed report storage (populated when callbacks fire)
        self.agent1_reports: dict[str, SurveillanceReport] = {}
        self.agent2_reports: dict[str, SwarmFindings] = {}
        self.latest_briefings: dict[str, IncidentBriefing] = {}

        # Asyncio Futures bridging callbacks → LangGraph nodes
        self._agent1_futures: dict[str, asyncio.Future] = {}
        self._agent2_futures: dict[str, asyncio.Future] = {}

        # Agent handles — agent1 and agent3 created once; agent2 per incident
        self.agent1 = None   # set by main.py after orchestrator init
        self.agent2 = None
        self.agent3 = AdvisoryAgent(agent3_model, self)

        # Event bus for world-event-driven Agent 3 re-triggers
        self.event_bus = EventBus(coalesce_window_s=0.5, heartbeat_interval_s=60.0)
        self._agent3_subscribed = False

        # LangGraph compiled graph — set by setup_graph()
        self._graph = None

        # Broadcast callback (set by main.py)
        self._broadcast_fn = None

    # ------------------------------------------------------------------
    # Public setup
    # ------------------------------------------------------------------

    async def setup_graph(self, checkpointer) -> None:
        """Build and compile the LangGraph state machine with SQLite checkpointer."""
        builder = StateGraph(ARIAState)

        builder.add_node("surveillance", self._surveillance_node)
        builder.add_node("swarm", self._swarm_node)
        builder.add_node("advisory", self._advisory_node)

        builder.add_edge(START, "surveillance")
        builder.add_edge("surveillance", "swarm")
        builder.add_edge("swarm", "advisory")
        builder.add_edge("advisory", END)

        self._graph = builder.compile(checkpointer=checkpointer)
        logger.info("langgraph_compiled", checkpointer=type(checkpointer).__name__)

    def set_broadcast(self, fn) -> None:
        self._broadcast_fn = fn
        if self.agent3:
            self.agent3.set_broadcast(fn)

    # ------------------------------------------------------------------
    # GO signal entry point
    # ------------------------------------------------------------------

    def receive_go_signal(self, payload: dict) -> dict:
        area = payload["area"]
        disaster_type = payload.get("disaster_type", "unknown")

        self.active_incident = {"area": area, "disaster_type": disaster_type}

        # Configure sensor overlay with center + radius (not polygon)
        if self.sensor_overlay:
            radius = area.get("radius_m", 500.0)
            self.sensor_overlay.set_incident(area["center"], radius, disaster_type)

        self.state = "SURVEILLANCE_ACTIVE"

        incident_id = f"INC-{int(time.time())}"
        initial_state: ARIAState = {
            "orchestrator_state": "SURVEILLANCE_ACTIVE",
            "incident_id": incident_id,
            "area": area,
            "disaster_type": disaster_type,
            "surveillance_report_json": None,
            "swarm_findings_json": None,
            "latest_advisory_json": None,
        }

        config = {"configurable": {"thread_id": incident_id}}
        asyncio.create_task(self._run_incident(initial_state, config))

        logger.info("go_signal_processed", incident_id=incident_id, disaster_type=disaster_type)
        return {"action": "go", "coordinates": area["center"], "incident_id": incident_id}

    async def _run_incident(self, initial_state: ARIAState, config: dict) -> None:
        if self._graph is None:
            logger.error("graph_not_compiled")
            return
        try:
            await self._graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            logger.error("incident_graph_error", error=str(exc), exc_info=True)

    # ------------------------------------------------------------------
    # LangGraph nodes
    # ------------------------------------------------------------------

    async def _surveillance_node(self, state: ARIAState) -> dict:
        incident_id = state["incident_id"]
        logger.info("surveillance_node_start", incident_id=incident_id)

        if self.agent1 is None:
            logger.error("agent1_not_wired")
            return {"orchestrator_state": "EMERGENCY"}

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._agent1_futures[incident_id] = future

        agent1_payload = {
            "action": "go",
            "coordinates": state["area"]["center"],
            "incident_id": incident_id,   # agent1 uses this ID in report_classification
        }
        await self.agent1.receive_go(agent1_payload)

        await self._broadcast({"type": "agent_log", "agent": "agent1",
                                "event": "survey_started",
                                "msg": f"Agent 1 surveying ({state['area']['center']['lat']:.4f}, {state['area']['center']['lon']:.4f})"})

        # Wait for agent1 to call back — state is checkpointed when this returns
        try:
            report_dict = await asyncio.wait_for(future, timeout=600.0)  # 10 min max
        except asyncio.TimeoutError:
            logger.error("surveillance_node_timeout", incident_id=incident_id)
            return {"orchestrator_state": "EMERGENCY"}
        self._agent1_futures.pop(incident_id, None)

        return {
            "orchestrator_state": "SWARM_ACTIVE",
            "surveillance_report_json": json.dumps(report_dict),
        }

    async def _swarm_node(self, state: ARIAState) -> dict:
        incident_id = state["incident_id"]
        surveillance_report_json = state.get("surveillance_report_json")

        if not surveillance_report_json:
            logger.error("swarm_node_no_report", incident_id=incident_id)
            return {"orchestrator_state": "EMERGENCY"}

        try:
            surveillance_report = SurveillanceReport.model_validate_json(surveillance_report_json)
        except Exception as exc:
            logger.error("surveillance_report_invalid", error=str(exc))
            return {"orchestrator_state": "EMERGENCY"}

        self.agent1_reports[incident_id] = surveillance_report
        classification = surveillance_report.classification
        logger.info("swarm_node_start", incident_id=incident_id, classification=classification)

        # Create swarm drones at home position
        swarm_count = _SWARM_COUNTS.get(classification, 2)
        swarm_type = _SWARM_TYPES.get(classification, "rotary")
        swarm_ids = []
        for i in range(swarm_count):
            sid = f"swarm-{i+1:03d}"
            if sid not in self.world_state.drones:
                self.world_state.add_drone(
                    sid, swarm_type,
                    self.world_state.home_position["lat"],
                    self.world_state.home_position["lon"],
                )
            swarm_ids.append(sid)

        # Create Agent 2 for this classification
        from agents.agent2_specialist import SpecialistAgent
        self.agent2 = SpecialistAgent(
            "agent2", self._agent2_model,
            self.world_state, self.sensor_overlay, self, classification,
        )
        self.agent2.drone_ids = swarm_ids
        if self._broadcast_fn:
            self.agent2.set_broadcast(self._broadcast_fn)

        # Subscribe Agent 3 to event bus (once per system start)
        if not self._agent3_subscribed:
            for ev in ("agent_1_report_received", "agent_2_findings_updated",
                       "world_event_fired", "operator_query", "heartbeat_check"):
                self.event_bus.subscribe(ev, self._handle_agent3_trigger)
            self._agent3_subscribed = True

        # Build initial briefing (no swarm data yet) and publish
        briefing = IncidentBriefing(
            incident_id=incident_id,
            trigger_type="agent_1_report_received",
            surveillance_report=surveillance_report,
            swarm_findings=None,
            previous_advisory=self.agent3.latest_advisory,
        )
        self.latest_briefings[incident_id] = briefing
        asyncio.create_task(self.event_bus.publish(
            "agent_1_report_received", {"incident_id": incident_id}
        ))
        asyncio.create_task(self.event_bus.start_heartbeat(
            incident_id,
            lambda: {"incident_id": incident_id},
        ))

        # Broadcast incident zone to UI
        asyncio.create_task(self._broadcast({
            "type": "incident",
            "data": {
                "incident_id": incident_id,
                "classification": classification,
                "confidence": surveillance_report.confidence,
                "center": surveillance_report.area.center,
                "radius_m": surveillance_report.area.radius_m,
            }
        }))

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._agent2_futures[incident_id] = future

        await self.agent2.receive_dispatch({
            "incident_id": incident_id,
            "center": state["area"]["center"],
        })

        # Wait for Agent 2 to report findings
        findings_dict = await future
        self._agent2_futures.pop(incident_id, None)

        return {
            "orchestrator_state": "ADVISORY_ACTIVE",
            "swarm_findings_json": json.dumps(findings_dict),
        }

    async def _advisory_node(self, state: ARIAState) -> dict:
        incident_id = state["incident_id"]
        logger.info("advisory_node_start", incident_id=incident_id)

        surveillance_report = self.agent1_reports.get(incident_id)
        if not surveillance_report and state.get("surveillance_report_json"):
            surveillance_report = SurveillanceReport.model_validate_json(
                state["surveillance_report_json"]
            )

        swarm_findings: SwarmFindings | None = None
        if state.get("swarm_findings_json"):
            try:
                swarm_findings = SwarmFindings.model_validate_json(state["swarm_findings_json"])
                self.agent2_reports[incident_id] = swarm_findings
            except Exception as exc:
                logger.warning("swarm_findings_parse_error", error=str(exc))

        briefing = IncidentBriefing(
            incident_id=incident_id,
            trigger_type="agent_2_findings_updated",
            surveillance_report=surveillance_report,
            swarm_findings=swarm_findings,
            previous_advisory=self.agent3.latest_advisory,
        )
        self.latest_briefings[incident_id] = briefing

        advisory = await self.agent3.on_trigger(briefing)

        await self._broadcast({"type": "advisory", "data": advisory})
        logger.info("advisory_issued", incident_id=incident_id)

        return {
            "orchestrator_state": "ADVISORY_ACTIVE",
            "latest_advisory_json": json.dumps(advisory),
        }

    # ------------------------------------------------------------------
    # Agent callbacks — resolve futures, bridging event-driven agents
    # into LangGraph nodes
    # ------------------------------------------------------------------

    def receive_agent1_report(self, report: dict) -> None:
        try:
            surveillance_report = SurveillanceReport(**report)
        except ValidationError as exc:
            logger.error("agent1_report_invalid", error=exc.json())
            return

        incident_id = surveillance_report.incident_id
        self.agent1_reports[incident_id] = surveillance_report
        self.state = "SWARM_ACTIVE"

        logger.info("agent1_report_received",
                    incident_id=incident_id,
                    classification=surveillance_report.classification,
                    confidence=surveillance_report.confidence)

        future = self._agent1_futures.pop(incident_id, None)
        if future is None and self._agent1_futures:
            # Fallback: pop first pending future (handles LLM-generated ID variance)
            key = next(iter(self._agent1_futures))
            future = self._agent1_futures.pop(key)
        if future and not future.done():
            future.set_result(report)
        else:
            logger.warning("agent1_no_pending_future", incident_id=incident_id)

    def receive_agent2_report(self, report: dict) -> None:
        try:
            swarm_findings = SwarmFindings(**report)
        except ValidationError as exc:
            logger.error("agent2_report_invalid", error=exc.json())
            return

        incident_id = swarm_findings.incident_id
        self.agent2_reports[incident_id] = swarm_findings
        self.state = "ADVISORY_ACTIVE"

        logger.info("agent2_report_received",
                    incident_id=incident_id,
                    coverage=swarm_findings.coverage_pct)

        # Update latest briefing with swarm findings
        briefing = self.latest_briefings.get(incident_id)
        if briefing:
            updated = IncidentBriefing(
                incident_id=incident_id,
                trigger_type="agent_2_findings_updated",
                surveillance_report=briefing.surveillance_report,
                swarm_findings=swarm_findings,
                previous_advisory=self.agent3.latest_advisory,
            )
            self.latest_briefings[incident_id] = updated
            asyncio.create_task(self.event_bus.publish(
                "agent_2_findings_updated", {"incident_id": incident_id}
            ))

        future = self._agent2_futures.pop(incident_id, None)
        if future is None and self._agent2_futures:
            key = next(iter(self._agent2_futures))
            future = self._agent2_futures.pop(key)
        if future and not future.done():
            future.set_result(report)
        else:
            logger.warning("agent2_no_pending_future", incident_id=incident_id)

    # ------------------------------------------------------------------
    # Event bus handler (world events → Agent 3 re-trigger)
    # ------------------------------------------------------------------

    async def _handle_agent3_trigger(self, payload: dict) -> None:
        incident_id = payload.get("incident_id")
        briefing = self.latest_briefings.get(incident_id) if incident_id else None
        if briefing is None:
            # Try any available briefing
            if self.latest_briefings:
                briefing = next(iter(self.latest_briefings.values()))
        if briefing is None:
            return
        advisory = await self.agent3.on_trigger(briefing)
        await self._broadcast({"type": "advisory", "data": advisory})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _broadcast(self, msg: dict) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(msg)
            except Exception:
                pass

    def get_incident_context(self) -> dict | None:
        return self.active_incident
