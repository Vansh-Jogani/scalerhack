# ARIA v1 — HANDOVER LOG

> Append-only running log. Newest entries at the **top**.
> Add an entry after: stage completion, blocker hit, architectural decision, end of session.
> Format below. Keep entries tight — full prose belongs in `CONTEXT.md`.

---

## [2026-05-16 02:00] — LangGraph + Stage 2 wiring complete
**Stage:** Stage 2 (in progress)
**State:** working — 138 tests passing, system boots, LangGraph compiled
**What got done:**
- LangGraph 1.2 + SQLite checkpointer integrated into orchestrator
  - ARIAState TypedDict persisted to aria_checkpoints.db
  - Graph: START → surveillance_node → swarm_node → advisory_node → END
  - Agent callbacks resolve asyncio Futures, bridging event-driven agents into LangGraph nodes
  - Crash recovery: state checkpointed after each node completes
- Sensor overlay changed from polygon to radius-based (set_incident takes center+radius_m)
  - Incident radius 600m in sendGo — drone hits it at any orbit radius
- WorldState: added zones/survivor_markers/hazard_markers + broadcast
- Agent 1: broadcast callbacks, tool_choice forces report_classification, loiter-to-center after classify
- Agents 2/3: set_broadcast + log events
- AdvisoryAgent constructor simplified (removed agent_id param)
- main.py: wires Agent1, LangGraph checkpointer, broadcasts zones/survivors
- frontend: agent stream log (colored A1/A2/A3/SYS), incident circle on map, zone circles, survivor markers
- Map: Leaflet (already was), animated drones with type-colored icons, incident zone circle
- requirements.txt: langgraph, langgraph-checkpoint-sqlite, aiosqlite, typing_extensions added
**What's next:**
- Test with ANTHROPIC_API_KEY: python main.py + npm run dev, then click GO
- Stage 2 checkpoints: 7-11 need live API to verify
- Stage 3: orchestrator multi-incident, Agent 2 full loop
**Blockers / open questions:**
- Needs ANTHROPIC_API_KEY in .env for live Agent 1/2/3 calls
**Files touched:**
- requirements.txt, orchestrator/orchestrator.py (full LangGraph rewrite)
- sim/sensor_overlay.py (radius-based), sim/world_state.py (zones/survivors/hazards)
- agents/agent1_surveillance.py (broadcast, tool_choice, loiter)
- agents/agent2_specialist.py (broadcast, incident_id init)
- agents/agent3_advisory.py (broadcast, simplified constructor)
- main.py (LangGraph checkpointer, Agent 1 wiring, zone broadcast)
- frontend/src/App.jsx (agent stream, incident display)
- frontend/src/Map.jsx (incident circle, zone circles, survivor markers)
- tests/test_sensor_and_tools.py (updated for radius-based API)

---

## [2026-05-16 01:10] — Integration Phase 5 complete — EventBus fully wired
**Stage:** Stage 1 (in progress) — integration all 5 phases done
**State:** working — 138 tests passing
**What got done:**
- Phase 5: EventBus fully wired in orchestrator:
  - receive_agent1_report: subscribes agent3 handler to all 5 trigger types (idempotent), publishes agent_1_report_received, starts heartbeat
  - receive_agent2_report: builds IncidentBriefing synchronously (latest_briefing updated before task fires), publishes agent_2_findings_updated via _publish_agent2_findings task
  - _handle_agent3_trigger: single handler for all bus events, calls agent3.on_trigger(latest_briefing), broadcasts advisory
  - 500ms coalescing verified: 3 rapid publishes -> 1 dispatch
  - Heartbeat: fires heartbeat_check after 60s silence (tested in test_event_bus.py)
- INTEGRATION_REPORT.md produced
**What's next:**
- IT-1 through IT-9 integration tests require ANTHROPIC_API_KEY for live LLM calls
- Full system test per FULL_SYSTEM_TEST.md when key is available
**Blockers / open questions:**
- Live integration tests (IT-4 through IT-9) need ANTHROPIC_API_KEY
**Files touched:**
- orchestrator/orchestrator.py (IncidentBriefing built synchronously in receive_agent2_report; _run_advisory -> _publish_agent2_findings)
**Notes for next session:**
- All typed boundaries tested and working without live API
- EventBus coalescing verified end-to-end

---

## [2026-05-16 00:55] — Integration Phase 4 complete — typed handoffs wired
**Stage:** Stage 1 (in progress) — integration phases 1–4 done
**State:** working — 138 tests passing
**What got done:**
- Phase 1: Copied 5 package test files into tests/ (138 total, all pass)
- Phase 2/3: Already complete (agents 1-3 already using load_prompt + Pydantic schemas)
- Phase 4: Typed handoffs wired:
  - agent1_surveillance._classify(): injects prompt_version_hash into report_classification call
  - agent2_specialist._handle_report_findings(): injects prompt_version_hash before forwarding to orchestrator
  - orchestrator.py rewritten: SurveillanceReport/SwarmFindings constructed at boundary with ValidationError rejection
  - orchestrator: Agent 2 instantiated dynamically on classification received (needs classification for constructor)
  - orchestrator: Agent 3 created once at init; IncidentBriefing constructed and passed typed to agent3.on_trigger
  - orchestrator: EventBus instantiated (not yet publisher-wired — that's Phase 5)
  - config.yaml: cleaned up stale Ollama keys, now models.agent2 + models.agent3 (both Claude API)
  - main.py: passes model strings from config to orchestrator constructor
**What's next:**
- Phase 5: Fully wire EventBus (agent_2_findings_updated publish path + verify coalescing)
**Blockers / open questions:**
- none
**Files touched:**
- agents/agent1_surveillance.py (prompt_version_hash injection)
- agents/agent2_specialist.py (prompt_version_hash injection)
- orchestrator/orchestrator.py (full typed handoff rewrite + EventBus init)
- main.py (model config passthrough)
- config.yaml (removed stale Ollama keys)
- tests/ (added 5 package test files)
**Notes for next session:**
- EventBus is instantiated in orchestrator and agent_1_report_received is published, but _run_advisory still calls event_bus.publish for agent_2_findings_updated — Phase 5 verifies the coalescing end-to-end

---

## [2026-05-16 00:45] — Build packaged for transfer to main PC
**Stage:** Stage 1 (in progress) — packaging complete
**State:** working — package verified, pushed
**What got done:**
- Verified all 11 deliverable files present
- Wrote 5 test files (77 tests) covering D1–D4 + isolation contract
- 77/77 passing in 1.94s from inside the clean package directory
- PACKAGE_NOTES.md written: hashes, decisions, deviations, env
- INTEGRATION.md included (provided by user)
- Stripped: __pycache__, .pyc, .pytest_cache — none present in archive
- Archive: prompts-comms-package.tar.gz (66,967 bytes, 36 files)
- TRANSFER_CHECKSUM.txt: SHA-256 = c26e5345a5c4e4eeab99702b320a615bd5ce596c12aa3fb452068f4b16db7b5b
- Branch: prompts-comms-package pushed to origin
- PR available at: github.com/Vansh-Jogani/scalerhack/pull/new/prompts-comms-package
**What's next:**
- Main PC: pull branch, extract archive, follow INTEGRATION.md 5-phase plan
- This machine: switch back to master, continue Stage 1 checkpoints 4–5
**Blockers / open questions:**
- none
**Files touched:**
- prompts-comms-package/ (new — 29 files)
- prompts-comms-package.tar.gz (new)
- TRANSFER_CHECKSUM.txt (new)
**Notes for next session:**
- The package is the transfer artifact — the 5 test files are the acceptance gate for integration
- EventBus still not wired into orchestrator.py — that's Phase 5 of INTEGRATION.md on the main PC

---

## [2026-05-16 00:05] — Prompt registry + typed comms layer complete (4 deliverables)
**Stage:** Stage 1 (in progress) — pre-Stage 2 infrastructure
**State:** working — all smoke tests passing
**What got done:**

**D1 — Prompt Registry**
- `prompts/registry.py`: load_prompt(name) returns {text, version_hash (8-char SHA-256)}
- Include resolution: `{{include: _shared/file.md}}` resolved at load time, not at runtime
- `fill_template()` for runtime `{{variable}}` substitution (Agent 2 swarm config)
- Cache-on-first-load; reload=True override for dev
- `prompts/agent1_surveillance.md`, `agent2_specialist.md`, `agent3_advisory.md` — all prompts in markdown, none inline in .py
- `prompts/_shared/safety_rules.md`, `output_contracts.md`, `notes.md`
- `notes.md` carries maritime_sar TODO for Stage 5 Agent 2 override

**D2 — Tool Schemas**
- `agents/tools/schemas.py`: Pydantic ToolInput base with to_claude_tool_dict() + validate_call()
- Agent 1: fly_to, loiter_over, get_sensor_reading, report_classification, request_detailed_pass
- Agent 2: deploy_swarm (batch, positions=[]), get_sensor_reading, update_zone_classification, mark_survivor, mark_hazard, report_swarm_findings
- Agent 3: issue_advisory (tool-use enforcement, not prompt-only JSON)
- AGENT_1_TOOLS, AGENT_2_TOOLS, AGENT_3_TOOLS lists exported for direct use
- Alt floor enforced: fly_to rejects alt < 60m at schema boundary

**D3 — Handoff Payload Schemas**
- `agents/messages.py`: SurveillanceReport, SwarmFindings, IncidentBriefing, WorldEvent
- All carry: incident_id, timestamp, agent_version, prompt_version_hash
- IncidentBriefing carries previous_advisory for Agent 3 update-not-restart semantics
- Round-trip serialization tested: model → JSON → model equality confirmed
- Validation rejection tested: confidence > 1.0 rejected at model boundary

**D4 — Event Bus**
- `orchestrator/event_bus.py`: async pub-sub, 500ms coalesce window (tunable)
- Coalescing confirmed: 3 events → 2 dispatches (one per type, latest payload wins)
- Heartbeat: fires heartbeat_check if no event in 60s — not a hard clock, resets on publish

**Agent 3 migration**
- Removed Ollama (httpx) entirely — now Claude API with tool_choice={"type":"tool","name":"issue_advisory"}
- Schema enforced at API boundary, not via prompt-only JSON instruction

**What's next:**
- Checkpoint 4: frontend drone icon moving on Mapbox (needs browser + token)
- Checkpoint 5: live Agent 1 API call (Anthropic key required)
- Wire EventBus into orchestrator.py (orchestrator.receive_agent1_report → bus.publish)
**Blockers / open questions:**
- Mapbox token for frontend checkpoint 4
- EventBus not yet wired into orchestrator.py — orchestrator still calls agent3 directly
**Files touched:**
- prompts/__init__.py (new)
- prompts/registry.py (new)
- prompts/agent1_surveillance.md (new)
- prompts/agent2_specialist.md (new)
- prompts/agent3_advisory.md (new)
- prompts/_shared/safety_rules.md (new)
- prompts/_shared/output_contracts.md (new)
- prompts/_shared/notes.md (new)
- agents/tools/schemas.py (new)
- agents/messages.py (new)
- orchestrator/event_bus.py (new)
- agents/agent1_surveillance.py (inline prompt removed, registry wired)
- agents/agent2_specialist.py (inline prompt removed, receive_dispatch + _run_mission added, AGENT_2_TOOLS wired)
- agents/agent3_advisory.py (Ollama removed, Claude API + tool use, registry wired)
**Notes for next session:**
- Agent 2 _run_mission() now has a full multi-turn tool loop — previously was a skeleton
- Agent isolation is enforced: Agent 2 receives SurveillanceReport (typed), not Agent 1 messages array
- Agent 3 receives IncidentBriefing (typed), not Agent 1 or 2 messages arrays
- prompt_version_hash logged with every LLM call for behavioral correlation

---

## [2026-05-15 22:40] — Stage 1 test suite created, 61/61 passing
**Stage:** Stage 1 (in progress)
**State:** working
**What got done:**
- Added `return_to_launch()` abstract method to `DroneInterface` (was missing — DroneModel had it, interface didn't enforce it)
- Created `pytest.ini` (asyncio_mode=auto)
- Created `tests/` directory with `conftest.py`, `__init__.py`
- `tests/test_drone_interface.py` — T3.5: ABC enforcement, DroneModel implements all abstract methods, MockSITLDrone stub, no agent imports DroneModel directly
- `tests/test_drone_model.py` — T3.1-T3.4: haversine math, 1km arrival timing (~55s ±2s), all class defaults, full state machine (IDLE→FLYING→LOITERING→RTL→IDLE), loiter hold, battery drain
- `tests/test_world_state.py` — add_drone, tick, command_drone, telemetry format, scenario load, malformed command rejection
- `tests/test_sensor_and_tools.py` — point_in_polygon, sensor readings per disaster type, fly_to handler ok/error, tick moves drone after command
- `tests/test_base_agent.py` — T4.1: observe pulls markers+telemetry, act executes tool_use blocks, full observe→reason→act cycle with mocked Anthropic client + real fly_to handler confirms drone enters FLYING
- Result: **61 passed, 0 failed** in 4.96s
**What's next:**
- Checkpoint 4: frontend drone icon moving on Mapbox map (needs browser + Mapbox token)
- Checkpoint 5: base_agent.py live loop test (Anthropic API key required)
- Checkpoint 6: confirmed via test_base_agent.py::test_run_one_cycle_with_mocked_client ✅
**Blockers / open questions:**
- Mapbox token required for frontend checkpoint 4
- Live Anthropic API test for checkpoint 5 (checkpoint 6 covered by mock test)
**Files touched:**
- sim/drone_interface.py (added return_to_launch abstract method)
- pytest.ini (new)
- tests/__init__.py (new)
- tests/conftest.py (new)
- tests/test_drone_interface.py (new)
- tests/test_drone_model.py (new)
- tests/test_world_state.py (new)
- tests/test_sensor_and_tools.py (new)
- tests/test_base_agent.py (new)
**Notes for next session:**
- Checkpoint 6 is proven by test; checkpoints 4-5 need live external services
- FULL_SYSTEM_TEST.md categories T3 and T4.1 are now implemented and green

---

## Entry template (copy this)

```
## [YYYY-MM-DD HH:MM] — <one-line summary>
**Stage:** <current stage>
**State:** <working / blocked / paused / in-progress>
**What got done:**
- bullet
- bullet
**What's next:**
- bullet
**Blockers / open questions:**
- bullet (or "none")
**Files touched:**
- path/to/file
**Notes for next session:**
- short note
```

---

## [2026-05-15 16:00] — Stage 1 scaffold + agent architecture implemented
**Stage:** Stage 1 (in progress)
**State:** working
**What got done:**
- Full directory scaffold: sim/, agents/, orchestrator/, sim_layer/, frontend/
- DroneModel kinematic (haversine movement, state machine, fixed-wing defaults)
- WorldState (Pydantic markers, drone management, tick loop)
- FastAPI + WebSocket server (health endpoint, telemetry broadcast, command handling)
- Orchestrator GO signal flow (holds full context, sends only coords to Agent 1)
- SensorOverlay with point-in-polygon trigger (ray casting)
- Agent 1 SurveillanceAgent with expanding circle survey pattern (50m→100m→150m)
- Agent 2 SpecialistAgent with SWARM_CAPABILITIES decision table
- Agent 3 AdvisoryAgent (Ollama, fallback mode, structured output)
- All tool schemas: fly_to, get_sensor_reading, report_classification, report_findings, issue_advisory
- All output schemas match spec (Changes 1-6 verified)
**What's next:**
- Verify full end-to-end: GO → Agent 1 survey → classify → Agent 2 → Agent 3 advisory
- Frontend: install npm deps, verify drone on map
- Checkpoints 4-6 full integration test
**Blockers / open questions:**
- Mapbox token needed for frontend testing (user must provide)
- Ollama must be running locally for Agent 3 live test (fallback works without it)
**Files touched:**
- sim/drone_interface.py, sim/drone_model.py, sim/world_state.py, sim/sensor_overlay.py
- sim/scenarios/fire.json
- agents/base_agent.py, agents/agent1_surveillance.py, agents/agent2_specialist.py, agents/agent3_advisory.py
- agents/tools/flight_tools.py, agents/tools/sensor_tools.py, agents/tools/report_tools.py
- orchestrator/orchestrator.py
- sim_layer/map_state_manager.py
- main.py, config.yaml, requirements.txt, .env.example, .gitignore
- frontend/ (package.json, vite.config.js, index.html, src/App.jsx, src/Map.jsx, src/main.jsx)
**Notes for next session:**
- Drone tick loop works in isolation but needs full server integration test for movement
- Agent 1 survey pattern verified with manual drone positioning; needs live tick loop test
- Stage 1 checkpoints 1-3 confirmed working (health, WS, markers, telemetry broadcast)

---

## [SETUP] — Project initialized
**Stage:** Pre-Stage-1
**State:** ready to start
**What got done:**
- SPEC.md, CONTEXT.md, HANDOVER.md placed in working directory
- Kickoff prompt prepared for Claude Code
**What's next:**
- Claude Code reads SPEC.md, CONTEXT.md, HANDOVER.md
- Enters Opus plan mode
- Produces Stage 1 plan
**Blockers / open questions:**
- Conventions to decide in Stage 1 plan: Python version, Node version, test framework, logging, secrets handling
**Files touched:**
- SPEC.md (created)
- CONTEXT.md (created)
- HANDOVER.md (created)
**Notes for next session:**
- Do not proceed past Stage 1 checkpoint 6 without explicit approval
- Use parallel subagents for scaffolding across sim/, agents/, orchestrator/, frontend/
