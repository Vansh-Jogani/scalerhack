"""ARIA Orchestrator — LangGraph state machine with SQLite checkpointer.

Graph: START → surveillance_node → swarm_node → relief_node → advisory_node → END
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
    relief_plan: Optional[dict]
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
        model_a4: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.model_a1 = model_a1
        self.model_a2 = model_a2
        self.model_a3 = model_a3
        self.model_a4 = model_a4
        self.state = "STANDBY"
        self.active_incident: dict | None = None
        self.event_callback = None
        self.agent1_report: dict | None = None
        self.agent2_report: dict | None = None
        self.agent4_report: dict | None = None
        self._agent1_future: asyncio.Future | None = None
        self._agent2_future: asyncio.Future | None = None
        self._agent4_future: asyncio.Future | None = None
        self.event_bus = EventBus()
        self.latest_briefing = None
        self._graph = None
        self._agent1_decision: dict | None = None

    def set_event_callback(self, callback) -> None:
        self.event_callback = callback

    def setup_graph(self, checkpointer) -> None:
        """Compile LangGraph graph with SQLite checkpointer."""
        from langgraph.graph import StateGraph, START, END

        builder = StateGraph(ARIAState)
        builder.add_node("surveillance", self._surveillance_node)
        builder.add_node("swarm", self._swarm_node)
        builder.add_node("relief", self._relief_node)
        builder.add_node("advisory", self._advisory_node)
        builder.add_edge(START, "surveillance")
        builder.add_edge("surveillance", "swarm")
        builder.add_edge("swarm", "relief")
        builder.add_edge("relief", "advisory")
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
            "dispatch_from": payload.get("dispatch_from"),
            "severity": payload.get("severity", "medium"),
        }
        self.agent1_report = None
        self.agent2_report = None
        self.latest_briefing = None
        self._agent1_decision = None

        if self.world_state:
            from sim.world_state import Marker
            self.world_state.add_marker(Marker(
                id=incident_id,
                lat=area["center"]["lat"],
                lon=area["center"]["lon"],
                type=disaster_type,
                radius_m=area.get("radius_m", 600.0),
                severity=payload.get("severity", "medium"),
                confirmed=True,
            ))

        if self.sensor_overlay:
            center = area["center"]
            radius_m = area.get("radius_m", 600.0)
            # Use ground_truth_type from the nearest marker (hidden from agents)
            ground_truth = self._lookup_ground_truth(center["lat"], center["lon"], disaster_type)
            self.sensor_overlay.set_incident(center["lat"], center["lon"], radius_m, ground_truth)
            actual_type = self._resolve_actual_disaster_type(center, disaster_type)
            self.sensor_overlay.set_incident(
                center["lat"], center["lon"], radius_m, actual_type
            )

        # Reposition drone-001 to the nearest response centre before launch
        dispatch_from = payload.get("dispatch_from")
        if dispatch_from and self.world_state:
            self.world_state.reposition_drone(
                "drone-001", dispatch_from["lat"], dispatch_from["lon"], 0.0
            )
            await self._emit("agent_stream", {
                "agent_id": "orchestrator",
                "event": "dispatch",
                "content": f"{dispatch_from['name']} — drone-001 assigned to {incident_id} · en route",
            })

        self.state = "SURVEILLANCE_ACTIVE"
        agent1_payload = {
            "action": "go",
            "coordinates": area["center"],
            "incident_id": incident_id,
            "type_hint": disaster_type,  # operator's guess — agent may revise
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

    def receive_agent1_decision(self, decision: dict) -> None:
        self._agent1_decision = decision
        logger.info("agent1_decision_received", decision=decision)

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

    def receive_agent4_report(self, report: dict) -> None:
        self.agent4_report = report
        logger.info("agent4_report_received", relief_type=report.get("relief_type"))
        if self._agent4_future and not self._agent4_future.done():
            self._agent4_future.set_result(report)

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
        coords = state["go_payload"].get("coordinates", {})
        hint = state["go_payload"].get("type_hint", "unknown")
        await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "pipeline_start", "content": f"LangGraph: START → surveillance · incident {state['incident_id']}"})
        await self._emit("agent_stream", {"agent_id": "agent-1", "event": "dispatched", "content": f"Fixed-wing en route · target ({coords.get('lat',0):.4f}, {coords.get('lon',0):.4f}) · operator hint: {hint}"})
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

        decision = self._agent1_decision or {}
        if decision.get("name") == "maintain_surveillance":
            reason = decision.get("reason", "")
            logger.info("swarm_skipped_agent1_decision", reason=reason)
            await self._emit("agent_stream", {
                "agent_id": "orchestrator",
                "event": "swarm_skipped",
                "content": f"Agent 1 → maintain surveillance. {reason}",
            })
            return {"agent2_findings": {}}

        classification = decision.get("swarm_type") or a1_report.get("classification", "fire")

        loop = asyncio.get_event_loop()
        self._agent2_future = loop.create_future()

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
        swarm_cfg = __import__('agents.agent2_specialist', fromlist=['SWARM_CAPABILITIES']).SWARM_CAPABILITIES.get(classification, {})
        await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "node_transition", "content": f"LangGraph: surveillance → swarm · A1 classified {classification}"})
        await self._emit("agent_stream", {"agent_id": "agent-2", "event": "dispatched", "content": f"Swarm selected: {swarm_cfg.get('swarm','?')} · {swarm_cfg.get('drones','?')} drones · alt {swarm_cfg.get('altitude','?')}m · constraint: {swarm_cfg.get('constraint','none')}"})
        await self._emit("agent_stream", {"agent_id": "agent-2", "event": "tools_loaded", "content": f"Tools: fly_to, find_nearest_base, launch_from_base, get_sensor_reading, report_findings"})
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

    async def _relief_node(self, state: ARIAState) -> dict:
        from agents.agent4_relief import ReliefAgent

        a2_report = state.get("agent2_findings") or {}
        classification = (state.get("agent1_report") or {}).get("classification", "fire")

        loop = asyncio.get_event_loop()
        self._agent4_future = loop.create_future()

        agent4 = ReliefAgent(
            agent_id=f"agent-4-{state['incident_id']}",
            model=self.model_a4,
            world_state=self.world_state,
            sensor_overlay=self.sensor_overlay,
            orchestrator=self,
            classification=classification,
            incident_id=state["incident_id"],
            stream_callback=self.event_callback,
            staging_lat=(self.active_incident or {}).get("dispatch_from", {}).get("lat"),
            staging_lon=(self.active_incident or {}).get("dispatch_from", {}).get("lon"),
            severity=(self.active_incident or {}).get("severity", "medium"),
        )
        await self._emit("agent_stream", {
            "agent_id": "agent-4", "event": "started",
            "content": f"Relief coordination — {classification}",
        })
        asyncio.create_task(agent4.run(a2_report))

        try:
            plan = await asyncio.wait_for(self._agent4_future, timeout=120.0)
        except asyncio.TimeoutError:
            logger.error("agent4_timeout")
            return {"relief_plan": {}}
        finally:
            self._agent4_future = None

        return {"relief_plan": plan if isinstance(plan, dict) else dict(plan)}

    async def _advisory_node(self, state: ARIAState) -> dict:
        from agents.agent3_advisory import AdvisoryAgent
        from agents.messages import IncidentBriefing

        self.state = "ADVISORY_ACTIVE"
        briefing = IncidentBriefing.from_dicts(
            incident_id=state["incident_id"],
            a1_data=state.get("agent1_report") or {},
            a2_data=state.get("agent2_findings") or {},
            a4_data=state.get("relief_plan") or None,
            previous_advisory=None,
        )
        self.latest_briefing = briefing

        await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "node_transition", "content": "LangGraph: swarm → advisory · all field data compiled"})
        agent3 = AdvisoryAgent(model=self.model_a3, orchestrator=self)
        await self._emit("agent_stream", {"agent_id": "agent-3", "event": "briefing_received", "content": f"Incident {state['incident_id']} · A1 + A2 data ingested · generating response plan"})
        advisory = await agent3.on_trigger(briefing)
        await self._emit("advisory", advisory)
        situation = advisory.get("situation_summary", "")
        actions = len(advisory.get("immediate_actions", []))
        flags = len(advisory.get("risk_flags", []))
        await self._emit("agent_stream", {"agent_id": "agent-3", "event": "advisory_issued", "content": f"Advisory issued · {actions} immediate actions · {flags} risk flags · {situation[:80]}…" if len(situation) > 80 else f"Advisory issued · {actions} immediate actions · {flags} risk flags"})
        await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "pipeline_complete", "content": f"LangGraph: advisory → END · mission pipeline complete"})
        return {"advisory": advisory}

    # ── EventBus integration ──────────────────────────────────────────────────

    async def _subscribe_and_publish_a1(self, report: dict) -> None:
        # Do NOT subscribe to agent_1_report_received — that fires Agent 3 before
        # Agent 2 runs, violating the LangGraph sequential pipeline.
        # Agent 3 initial advisory is handled exclusively by _advisory_node.
        # EventBus only handles post-advisory updates (A2 new findings, world events).
        for trigger in [
            "agent_2_findings_updated",
            "world_event_fired",
            "operator_query",
            "heartbeat_check",
        ]:
            self.event_bus.subscribe(trigger, self._handle_agent3_trigger)
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
            a4_data=self.agent4_report or None,
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
                a4_data=self.agent4_report or None,
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
                    "relief_plan": None,
                    "advisory": None,
                    "error": None,
                },
                config={"configurable": {"thread_id": incident_id}},
            )
        except Exception as e:
            logger.error("graph_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "error", "content": str(e)})
        finally:
            await self._recall_all_drones(incident_id)

    async def _run_incident_stack_fallback(self, agent1_payload: dict) -> None:
        """Fallback sequential pipeline when LangGraph is not available."""
        from agents.agent1_surveillance import SurveillanceAgent
        from agents.agent2_specialist import SpecialistAgent
        from agents.agent3_advisory import AdvisoryAgent
        from agents.agent4_relief import ReliefAgent
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
                staging_lat=(self.active_incident or {}).get("dispatch_from", {}).get("lat"),
                staging_lon=(self.active_incident or {}).get("dispatch_from", {}).get("lon"),
            )
            await self._emit("agent_stream", {"agent_id": "agent-2", "event": "started", "content": f"Deploying {classification} swarm"})
            await agent2.run(self.agent1_report or {})

            agent4 = ReliefAgent(
                agent_id="agent-4", model=self.model_a4,
                world_state=self.world_state, sensor_overlay=self.sensor_overlay,
                orchestrator=self, classification=classification, incident_id=incident_id,
                stream_callback=self.event_callback,
                staging_lat=(self.active_incident or {}).get("dispatch_from", {}).get("lat"),
                staging_lon=(self.active_incident or {}).get("dispatch_from", {}).get("lon"),
                severity=(self.active_incident or {}).get("severity", "medium"),
            )
            await self._emit("agent_stream", {"agent_id": "agent-4", "event": "started", "content": f"Relief coordination — {classification}"})
            await agent4.run(self.agent2_report or {})
            self.state = "ADVISORY_ACTIVE"

            briefing = IncidentBriefing.from_dicts(
                incident_id=incident_id,
                a1_data=self.agent1_report or {},
                a2_data=self.agent2_report or {},
                a4_data=self.agent4_report or None,
            )
            agent3 = AdvisoryAgent(model=self.model_a3, orchestrator=self)
            await self._emit("agent_stream", {"agent_id": "agent-3", "event": "started", "content": "Generating advisory"})
            advisory = await agent3.on_trigger(briefing)
            await self._emit("advisory", advisory)

        except Exception as e:
            logger.error("incident_stack_error", error=str(e), exc_info=True)
            await self._emit("agent_stream", {"agent_id": "orchestrator", "event": "error", "content": str(e)})

    def _lookup_ground_truth(self, lat: float, lon: float, fallback: str) -> str:
        """Find ground_truth_type from the nearest world_state marker."""
        import math
        def _dist(m):
            dlat = math.radians(m.lat - lat)
            dlon = math.radians(m.lon - lon)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(m.lat)) * math.sin(dlon / 2) ** 2
            return 6_371_000.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        markers = self.world_state.markers if self.world_state else []
        if not markers:
            return fallback
        nearest = min(markers, key=_dist)
        return nearest.ground_truth_type or nearest.type

    async def _emit(self, event_type: str, data: dict) -> None:
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.warning("emit_error", event_type=event_type, error=str(e))

    async def _recall_all_drones(self, incident_id: str) -> None:
        """RTL drones that are low-battery or unneeded; redirect others to recon remaining incidents."""
        import math

        if not self.world_state:
            return
        self.state = "STANDBY"

        def _dist(lat1, lon1, lat2, lon2):
            R = 6_371_000.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        LOW_BATTERY = 20.0
        remaining = [m for m in self.world_state.markers if m.id != incident_id]
        drone_ids = list(self.world_state.drones.keys())
        recalled, redirected = [], []

        for drone_id in drone_ids:
            drone = self.world_state.drones.get(drone_id)
            if not drone or drone.get_state() in ("IDLE", "RTL"):
                continue

            if drone.battery_pct <= LOW_BATTERY:
                drone.return_to_launch()
                recalled.append(drone_id)
            elif remaining:
                nearest = min(remaining, key=lambda m: _dist(drone.lat, drone.lon, m.lat, m.lon))
                cruise_alt = drone._defaults.get("cruise_alt") or drone._defaults.get("hover_alt", 30.0)
                self.world_state.command_drone(drone_id, nearest.lat, nearest.lon, cruise_alt)
                redirected.append((drone_id, nearest.id))
            else:
                drone.return_to_launch()
                recalled.append(drone_id)

        parts = []
        if recalled:
            parts.append(f"{len(recalled)} RTL (low-battery or no tasks)")
        if redirected:
            parts.append(f"{len(redirected)} redirected to recon " + ", ".join(f"{d}→{m}" for d, m in redirected))
        summary = "; ".join(parts) if parts else "no active drones"

        logger.info("incident_resolved_drone_status", incident_id=incident_id, recalled=len(recalled), redirected=len(redirected))
        await self._emit("agent_stream", {
            "agent_id": "orchestrator",
            "event": "incident_resolved",
            "content": f"Incident {incident_id} resolved — {summary}",
        })

    def _resolve_actual_disaster_type(self, center: dict, operator_guess: str) -> str:
        """Return the nearest scenario marker's type as ground truth.

        The operator's disaster_type selection is their hypothesis — the scenario
        marker is what actually happened. If the drone is dispatched within 5km of
        a known marker, use the marker's type so sensor data reflects reality.
        """
        import math

        if not self.world_state or not self.world_state.markers:
            return operator_guess

        def _hav(lat1, lon1, lat2, lon2):
            R = 6_371_000.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        nearest = min(
            self.world_state.markers,
            key=lambda m: _hav(center["lat"], center["lon"], m.lat, m.lon),
        )
        dist = _hav(center["lat"], center["lon"], nearest.lat, nearest.lon)

        if dist <= 5000:
            if nearest.type != operator_guess:
                logger.info(
                    "operator_misclassification",
                    operator_guess=operator_guess,
                    actual=nearest.type,
                    dist_m=round(dist),
                )
            return nearest.type

        return operator_guess
