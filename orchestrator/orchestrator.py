"""ARIA Orchestrator — LangGraph deterministic state machine.

NOT an LLM. A deterministic state machine — fast, reliable, crash-safe.
Uses LangGraph StateGraph + SQLite checkpointer per SPEC.md.

States: STANDBY, SURVEILLANCE_ACTIVE, SWARM_ACTIVE, ADVISORY_ACTIVE,
        MULTI_INCIDENT, EMERGENCY
"""

import asyncio
import os
from pathlib import Path
from typing import TypedDict, Any

import structlog
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from orchestrator.classifier import classify
from orchestrator.incident_manager import IncidentManager

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# State schema — strict sub-key ownership
# ---------------------------------------------------------------------------

class IncidentState(TypedDict, total=False):
    """LangGraph state. Each agent writes ONLY to its designated sub-key."""
    orchestrator: dict       # orchestrator writes here only
    sensor_readings: dict    # Agent 1 writes here only
    map_layers: dict         # Agent 2 writes here only
    comms_log: dict          # Agent 3 writes here only
    drone_events: dict       # drone controller writes here only
    active_incidents: list
    current_state: str


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ARIAOrchestrator:
    """Deterministic state machine for incident management.

    No LLM calls in this class — ever. Transitions are conditional edges
    based on state values.
    """

    STATES = [
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
        model: str = "claude-sonnet-4-20250514",
        agent3_model: str = "claude-sonnet-4-20250514",
    ):
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.model = model
        self.agent3_model = agent3_model

        self.state = "STANDBY"
        self.event_callback = None
        self.incident_manager = IncidentManager()

        # Reports stored for inter-agent data flow (via orchestrator, not cross-agent)
        self.agent1_report: dict | None = None
        self.agent2_report: dict | None = None
        self.active_incident: dict | None = None

        # SQLite checkpointer setup
        self._db_path = Path("state")
        self._db_path.mkdir(exist_ok=True)
        self._checkpointer_path = str(self._db_path / "aria_state.db")

        # Build the LangGraph state machine (checkpointer wired in async init)
        self._graph = self._build_graph()
        self._checkpointer: AsyncSqliteSaver | None = None

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph StateGraph with deterministic transitions.

        Checkpointer is wired lazily in _run_graph via AsyncSqliteSaver context manager.
        """
        graph = StateGraph(IncidentState)

        # Add nodes — each is a deterministic function, NOT an LLM
        graph.add_node("standby", self._standby_node)
        graph.add_node("surveillance", self._surveillance_node)
        graph.add_node("classify", self._classify_node)
        graph.add_node("swarm", self._swarm_node)
        graph.add_node("advisory", self._advisory_node)
        graph.add_node("emergency", self._emergency_node)

        # Set entry point
        graph.set_entry_point("standby")

        # Add edges — deterministic transitions
        graph.add_edge("standby", "surveillance")
        graph.add_edge("surveillance", "classify")
        graph.add_edge("classify", "swarm")
        graph.add_edge("swarm", "advisory")
        graph.add_edge("advisory", END)
        graph.add_edge("emergency", END)

        return graph.compile()

    def _build_graph_with_checkpointer(self, checkpointer) -> StateGraph:
        """Compile the graph with a live SQLite checkpointer for crash-safe persistence."""
        graph = StateGraph(IncidentState)
        graph.add_node("standby", self._standby_node)
        graph.add_node("surveillance", self._surveillance_node)
        graph.add_node("classify", self._classify_node)
        graph.add_node("swarm", self._swarm_node)
        graph.add_node("advisory", self._advisory_node)
        graph.add_node("emergency", self._emergency_node)
        graph.set_entry_point("standby")
        graph.add_edge("standby", "surveillance")
        graph.add_edge("surveillance", "classify")
        graph.add_edge("classify", "swarm")
        graph.add_edge("swarm", "advisory")
        graph.add_edge("advisory", END)
        graph.add_edge("emergency", END)
        return graph.compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------
    # Node functions — deterministic, NO LLM calls
    # ------------------------------------------------------------------

    async def _standby_node(self, state: IncidentState) -> dict:
        """Entry node. Prepares state for the incident stack."""
        self.state = "STANDBY"
        logger.info("orchestrator_node", node="standby", state=self.state)
        return {
            "current_state": "STANDBY",
            "orchestrator": state.get("orchestrator", {}),
        }

    async def _surveillance_node(self, state: IncidentState) -> dict:
        """Run Agent 1 Surveillance."""
        from agents.agent1_surveillance import SurveillanceAgent

        self.state = "SURVEILLANCE_ACTIVE"
        logger.info("orchestrator_node", node="surveillance", state=self.state)

        await self._emit("agent_stream", {
            "agent_id": "agent-1", "event": "started",
            "content": state.get("orchestrator", {}).get("agent1_payload", {}),
        })

        agent1_payload = state.get("orchestrator", {}).get("agent1_payload", {})
        drone_id = "drone-001"

        agent1 = SurveillanceAgent(
            agent_id="agent-1",
            model=self.model,
            world_state=self.world_state,
            sensor_overlay=self.sensor_overlay,
            orchestrator=self,
            drone_id=drone_id,
            stream_callback=self.event_callback,
        )

        try:
            await agent1.receive_go(agent1_payload)
        except Exception as e:
            logger.error("agent1_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {
                "agent_id": "agent-1", "event": "error", "content": str(e),
            })

        return {
            "current_state": "SURVEILLANCE_ACTIVE",
            "sensor_readings": {
                "agent1_report": self.agent1_report or {},
            },
        }

    async def _classify_node(self, state: IncidentState) -> dict:
        """Classify incident type → swarm config. NO LLM."""
        report = self.agent1_report or {}
        incident_type = report.get("classification", "fire")

        try:
            swarm_config = classify(incident_type)
        except ValueError as e:
            logger.error("classifier_error", error=str(e))
            swarm_config = classify("fire")  # fallback to fire

        logger.info("orchestrator_node", node="classify",
                    incident_type=incident_type,
                    swarm=swarm_config["swarm"])

        orch_state = state.get("orchestrator", {})
        orch_state["swarm_config"] = swarm_config
        orch_state["classification"] = incident_type

        return {
            "orchestrator": orch_state,
        }

    async def _swarm_node(self, state: IncidentState) -> dict:
        """Run Agent 2 Specialist Swarm."""
        from agents.agent2_specialist import SpecialistAgent

        self.state = "SWARM_ACTIVE"
        orch_state = state.get("orchestrator", {})
        swarm_config = orch_state.get("swarm_config", classify("fire"))
        classification = orch_state.get("classification", "fire")

        logger.info("orchestrator_node", node="swarm", state=self.state,
                    swarm=swarm_config["swarm"])

        await self._emit("agent_stream", {
            "agent_id": "agent-2", "event": "started",
            "content": f"Deploying {classification} swarm ({swarm_config['swarm']})",
        })

        agent2 = SpecialistAgent(
            agent_id="agent-2",
            model=self.model,
            world_state=self.world_state,
            sensor_overlay=self.sensor_overlay,
            orchestrator=self,
            swarm_config=swarm_config,
            classification=classification,
            stream_callback=self.event_callback,
        )

        try:
            await agent2.run_mission(self.agent1_report or {})
        except Exception as e:
            logger.error("agent2_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {
                "agent_id": "agent-2", "event": "error", "content": str(e),
            })

        return {
            "current_state": "SWARM_ACTIVE",
            "map_layers": {
                "agent2_report": self.agent2_report or {},
            },
        }

    async def _advisory_node(self, state: IncidentState) -> dict:
        """Run Agent 3 Advisory."""
        from agents.agent3_advisory import AdvisoryAgent

        self.state = "ADVISORY_ACTIVE"
        logger.info("orchestrator_node", node="advisory", state=self.state)

        await self._emit("agent_stream", {
            "agent_id": "agent-3", "event": "started",
            "content": "Generating advisory",
        })

        agent3 = AdvisoryAgent(
            agent_id="agent-3",
            model=self.agent3_model,
            orchestrator=self,
            stream_callback=self.event_callback,
        )

        advisory: dict = {}
        try:
            advisory = await agent3.on_trigger(
                trigger_type="agent_2_findings_updated",
                agent1_report=self.agent1_report or {},
                agent2_report=self.agent2_report or {},
            )
            await self._emit("advisory", advisory)
            await self._emit("agent_stream", {
                "agent_id": "agent-3", "event": "advisory_issued",
                "content": advisory.get("situation_summary", advisory.get("text", "")),
            })
        except Exception as e:
            logger.error("agent3_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {
                "agent_id": "agent-3", "event": "error", "content": str(e),
            })

        return {
            "current_state": "ADVISORY_ACTIVE",
            "comms_log": {
                "latest_advisory": advisory,
            },
        }

    async def _emergency_node(self, state: IncidentState) -> dict:
        """Emergency abort — RTL all drones."""
        from agents.tools.flight_tools import create_abort_handler

        self.state = "EMERGENCY"
        logger.info("orchestrator_node", node="emergency", state=self.state)

        abort = create_abort_handler(self.world_state)
        for drone_id in list(self.world_state.drones.keys()):
            try:
                await abort(drone_id=drone_id)
                logger.info("emergency_abort", drone_id=drone_id)
            except Exception as e:
                logger.error("abort_failed", drone_id=drone_id, error=str(e))

        return {"current_state": "EMERGENCY"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_event_callback(self, callback) -> None:
        """Register async callback for broadcasting events to connected clients."""
        self.event_callback = callback

    async def receive_go_signal(self, payload: dict) -> dict:
        """Process GO signal from operator.

        Stores full area context. Runs the LangGraph state machine as a
        background task. Returns stripped payload for Agent 1 immediately.
        """
        area = payload.get("area", {})
        disaster_type = payload.get("disaster_type", "unknown")

        self.active_incident = {
            "area": area,
            "disaster_type": disaster_type,
        }
        self.agent1_report = None
        self.agent2_report = None

        # Set up sensor overlay with incident boundary
        if self.sensor_overlay and "boundary_polygon" in area:
            self.sensor_overlay.set_incident(area["boundary_polygon"], disaster_type)

        # Stripped payload for Agent 1 (coordinates only)
        agent1_payload = {
            "action": "go",
            "coordinates": area.get("center", {}),
        }

        logger.info(
            "go_signal_processed",
            state=self.state,
            disaster_type=disaster_type,
            center=area.get("center"),
        )

        # Register with incident manager
        marker = area.get("center", {})
        marker["id"] = f"INC-{disaster_type}"
        marker["type"] = disaster_type
        self.incident_manager.on_new_marker(marker)

        # Run the full state machine as a background task
        initial_state: IncidentState = {
            "orchestrator": {
                "agent1_payload": agent1_payload,
                "disaster_type": disaster_type,
                "area": area,
            },
            "sensor_readings": {},
            "map_layers": {},
            "comms_log": {},
            "drone_events": {},
            "active_incidents": [],
            "current_state": "STANDBY",
        }

        asyncio.create_task(self._run_graph(initial_state))
        return agent1_payload

    async def _run_graph(self, initial_state: IncidentState) -> None:
        """Execute the LangGraph state machine with SQLite checkpointer."""
        try:
            async with AsyncSqliteSaver.from_conn_string(self._checkpointer_path) as checkpointer:
                graph = self._build_graph_with_checkpointer(checkpointer)
                config = {"configurable": {"thread_id": f"incident-{id(initial_state)}"}}
                result = await graph.ainvoke(initial_state, config=config)
            self.state = result.get("current_state", "STANDBY")
            logger.info("graph_completed", final_state=self.state)
        except Exception as e:
            logger.error("graph_error", error=str(e), exc_info=True)
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
                model=self.agent3_model,
                orchestrator=self,
                stream_callback=self.event_callback,
            )
            advisory = await agent3.on_trigger(
                trigger_type="world_event_fired",
                agent1_report=self.agent1_report,
                agent2_report=self.agent2_report or {},
            )
            await self._emit("advisory", advisory)

    def receive_agent1_report(self, report: dict) -> None:
        """Receive classification report from Agent 1.

        Enriches the report with area context from active_incident so Agent 2
        knows where to deploy its swarm.
        """
        # Enrich with area context — Agent 2 needs center + radius_m
        if self.active_incident:
            area = self.active_incident.get("area", {})
            report["area"] = {
                "center": area.get("center", {}),
                "radius_m": area.get("radius_m", 200.0),
            }
        self.agent1_report = report
        logger.info("agent1_report_received",
                    classification=report.get("classification"),
                    confidence=report.get("confidence"))

    def receive_agent2_report(self, report: dict) -> None:
        """Receive findings report from Agent 2."""
        self.agent2_report = report
        logger.info("agent2_report_received",
                    coverage=report.get("coverage_pct"))

    async def on_go_signal(self, marker: dict, confidence: float = 100.0,
                           signal_sources: list | None = None,
                           zone_polygon: list | None = None) -> dict:
        """Entry point for AlertDetector autonomous dispatch.

        Translates the WorldState marker schema into the receive_go_signal
        payload format, then delegates to the existing pipeline.

        Args:
            marker: {id, lat, lon, type, radius_m, severity, confirmed}
            confidence: fused confidence score (0–100)
            signal_sources: list of source names that contributed
            zone_polygon: optional drawn zone vertices from admin panel
        """
        logger.info(
            "on_go_signal",
            marker_id=marker.get("id"),
            lat=marker.get("lat"),
            lon=marker.get("lon"),
            disaster_type=marker.get("type"),
            confidence=confidence,
            signal_sources=signal_sources or [],
        )

        area: dict = {
            "center": {
                "lat": marker["lat"],
                "lon": marker["lon"],
            },
            "radius_m": marker.get("radius_m", 500.0),
        }
        if zone_polygon:
            area["boundary_polygon"] = zone_polygon

        payload = {
            "area": area,
            "disaster_type": marker.get("type", "unknown"),
            "alert_metadata": {
                "confidence": confidence,
                "signal_sources": signal_sources or [],
                "marker_id": marker.get("id"),
                "confirmed": marker.get("confirmed", False),
                "severity": marker.get("severity", "medium"),
            },
        }

        return await self.receive_go_signal(payload)

    def get_incident_context(self) -> dict | None:
        """Return full incident context (used by sensor overlay, not agents)."""
        return self.active_incident

    async def emergency_abort(self) -> None:
        """Trigger emergency abort of all drones."""
        await self._emergency_node({})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _emit(self, event_type: str, data: dict) -> None:
        """Emit event to WebSocket broadcast callback."""
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.warning("emit_error", event_type=event_type, error=str(e))
