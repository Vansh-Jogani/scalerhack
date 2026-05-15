# ARIA v1 — HANDOVER LOG

> Append-only running log. Newest entries at the **top**.
> Add an entry after: stage completion, blocker hit, architectural decision, end of session.
> Format below. Keep entries tight — full prose belongs in `CONTEXT.md`.

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
