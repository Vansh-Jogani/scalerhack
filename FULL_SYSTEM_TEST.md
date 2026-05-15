# ARIA v1 — FULL SYSTEM TEST & TROUBLESHOOTING PROTOCOL

> **When to run:** Only after Stage 5 is complete. This is the final acceptance gate.
> **How to run:** Paste the kickoff block below as a single message to Claude Code. Then let it work.
> **Goal:** Every test passes. No exceptions. No "good enough." If something fails, Claude fixes it and re-runs until green.

---

## KICKOFF BLOCK (paste this to Claude Code)

```
You are running ARIA v1 final system validation. Read FULL_SYSTEM_TEST.md completely before doing anything.

Operating rules for this run:
1. Enter Opus plan mode. Produce a test execution plan covering all 9 test categories. Present it. Wait for my approval.
2. After approval, execute tests in the order specified. Do not skip ahead.
3. For every failure: stop, diagnose root cause (not symptom), fix, re-run the failed test, then re-run all preceding tests to confirm no regression.
4. Use parallel subagents for: log collection across services, independent unit test categories, library/API behavior verification. Never parallelize tests that share state or write to the same files.
5. Update HANDOVER.md after every test category completes (pass or fail-then-fixed).
6. Do NOT mark a test "passed with caveats." A test either passes cleanly or it fails and gets fixed.
7. At the end, produce SYSTEM_TEST_REPORT.md with full results.

If you find that a fix would require violating SPEC.md, STOP and ask. Do not silently re-architect.

Begin by reading SPEC.md, CONTEXT.md, last 5 HANDOVER.md entries, then FULL_SYSTEM_TEST.md. Then plan.
```

---

## TEST PHILOSOPHY

This is not a checkbox exercise. The system has nine surfaces where things break:

1. **Process lifecycle** — does everything start, stay running, and shut down clean?
2. **Data contracts** — does the simulation share exactly what the spec says, and hide what the spec says to hide?
3. **Drone physics** — do drones move the way the kinematic model promises?
4. **Agent reasoning loops** — do agents observe, reason, and act correctly through their tool sets?
5. **Orchestration** — does the LangGraph state machine transition states correctly and survive crashes?
6. **Map rendering** — does the single-writer MapStateManager actually prevent the concurrent-update glitch?
7. **End-to-end flow** — does a marker actually produce an advisory, every time?
8. **Multi-incident handling** — does the system not collapse under 2+ simultaneous markers?
9. **Failure modes** — do the documented fallbacks actually work when their failure mode is induced?

Tests are ordered cheapest-first. A failure at layer N invalidates everything above it — fix and restart from layer N.

---

## TEST CATEGORY 1 — Process lifecycle & smoke

**Goal:** Everything starts. Everything stops. No zombie processes.

### T1.1 — Clean start from `main.py`
- [ ] `python main.py` (or equivalent) launches without error
- [ ] FastAPI process is reachable on configured port
- [ ] WebSocket endpoint accepts a connection and echoes a heartbeat
- [ ] Frontend dev server (Vite/Next/whatever was chosen in Stage 1) starts and serves the operator UI
- [ ] Ollama is reachable at `http://localhost:11434/api/chat` with `llama3.1:8b` loaded
- [ ] SQLite checkpointer file is created in the expected location

**Failure diagnosis:** Capture stderr from each process. Common causes: port collision, missing env var (ANTHROPIC_API_KEY), Ollama model not pulled, frontend build error from a missed dependency.

### T1.2 — Clean shutdown
- [ ] Ctrl-C / SIGTERM stops all processes within 5 seconds
- [ ] No orphan child processes left running (`ps aux | grep -E "aria|uvicorn|node"` returns nothing unexpected)
- [ ] No locked SQLite file preventing restart
- [ ] Subsequent `python main.py` starts cleanly

**Failure diagnosis:** If child processes survive, the parent is not propagating signals. Fix: handle SIGINT/SIGTERM in the supervisor.

### T1.3 — Restart resilience
- [ ] Kill the orchestrator process mid-run (`kill -9` while an incident is active)
- [ ] On restart, LangGraph SQLite checkpointer restores the last clean state
- [ ] No drone is left in an undefined state (all drones report a valid state from the spec's enum)

**Acceptance:** All three pass cleanly. No flakiness tolerated.

---

## TEST CATEGORY 2 — Data contract validation

**Goal:** The simulation/agent boundary is exactly what the spec says — no more, no less.

### T2.1 — `SHARED_TO_AGENTS` contract
For each field in the spec's `SHARED_TO_AGENTS` dict (`markers`, `drone_telemetry`, `sensor_data`):
- [ ] The field is reachable from an agent's tool call
- [ ] Type matches the spec exactly
- [ ] No extra fields leak through (write a test that asserts the keyset equals the spec's keyset)

### T2.2 — `HIDDEN_FROM_AGENTS` contract
Write an assertion test that explicitly attempts to access each of:
- [ ] `world_seed` — must raise or return `None`/forbidden, never the real value
- [ ] `other_agent_reasoning` — Agent 1 cannot read Agent 2's LLM context, and vice versa
- [ ] `future_world_events` — fire growth schedule, aftershock timing, etc. are not in any payload reaching an agent
- [ ] `full_zone_graph` — agents only see zones they've flown over

**Failure diagnosis:** If anything leaks, the failure is almost always a serialization shortcut — someone passed the whole world state object into a tool. Fix at the serialization boundary, not the agent.

### T2.3 — `SHARED_TO_SIMULATION` contract
- [ ] Agents can issue `fly_to`, `loiter_over`, `rtl`, `abort` and the world state reflects the command
- [ ] Agents can write `zone_classification`, `survivor_marker`, `hazard_marker` and they appear in the world state
- [ ] Malformed commands are rejected (e.g., `fly_to` without lat/lon) — agent receives a tool error, world state is unchanged

**Acceptance:** All three pass. Bonus: enforce the contract with a Pydantic schema at the boundary so it's structurally impossible to drift.

---

## TEST CATEGORY 3 — Drone kinematics

**Goal:** The kinematic model behaves like a drone, not a teleporter or a glitching dot.

### T3.1 — Position update mechanics
- [ ] Issue `fly_to` for a point 1km away to a fixed-wing drone (18 m/s cruise)
- [ ] Expected arrival time: ~55 seconds. Measured arrival within ±2 seconds
- [ ] Position is updated every tick, not just at start/end
- [ ] Heading rotates smoothly during turns, not instantaneously

### T3.2 — Drone class defaults respected
For each class (fixed-wing, rotary, micro-rotary):
- [ ] Cruise speed matches spec exactly
- [ ] Cruise/hover altitude matches spec exactly
- [ ] Loiter radius (fixed-wing) or loiter time (rotary) matches spec

### T3.3 — Drone state machine
- [ ] `IDLE → FLYING` on `fly_to`
- [ ] `FLYING → LOITERING` on arrival + `loiter_over` command
- [ ] `LOITERING → RTL` on `rtl`
- [ ] `RTL → IDLE` on arrival at home
- [ ] `FLYING → THERMAL_SCAN` is reachable from the fire scenario
- [ ] Invalid transitions are rejected (e.g., `IDLE → LOITERING` without flying first)

### T3.4 — Loiter pattern correctness
- [ ] Fixed-wing drone in loiter executes circular orbit at the specified radius
- [ ] Rotary drone in loiter hovers within a 5m radius of target
- [ ] One full orbit takes the expected time given speed and radius

### T3.5 — DroneInterface abstraction
- [ ] `DroneInterface` is an actual abstract base class (ABC) — instantiating it directly raises
- [ ] `DroneModel` implements every abstract method
- [ ] No agent code imports `DroneModel` directly — agents only touch `DroneInterface`-typed handles
- [ ] (Smoke test for V2 readiness) Create a stub `MockSITLDrone(DroneInterface)` with empty methods — it must satisfy the type checker

**Acceptance:** All pass. T3.5 is the V2-readiness gate and is non-negotiable.

---

## TEST CATEGORY 4 — Agent reasoning loops

**Goal:** Each agent observes correctly, reasons coherently, and acts through its tool set.

### T4.1 — `base_agent.py` loop primitive
- [ ] Observe phase pulls sensor data + telemetry from world state
- [ ] Reason phase produces a tool call (or terminal report)
- [ ] Act phase executes the tool call and writes the result back to context
- [ ] Loop terminates on `report_classification` or `issue_advisory` — no infinite spinning

### T4.2 — Agent 1 (Surveillance, Claude API)
Run the surveillance scenario in isolation with a single fire marker:
- [ ] Agent receives the go signal with coordinates
- [ ] Agent calls `fly_to` toward the marker
- [ ] On overflight, agent calls `get_sensor_reading`
- [ ] Agent completes at least one full orbit before reporting (spec rule)
- [ ] Agent calls `report_classification` with type, confidence, and affected area
- [ ] Agent never commands the drone below 60m AGL (spec rule)
- [ ] Agent flags marker area growth if induced

**Failure diagnosis:** If agent classifies before orbiting, the system prompt or tool set is letting it short-circuit — tighten the prompt or remove premature reporting.

### T4.3 — Agent 2 (Specialist Swarm, Claude API)
For at least the fire and structural_collapse scenarios:
- [ ] Swarm type is selected from `SWARM_CAPABILITIES` table — agent is NOT asked to choose
- [ ] Correct number of drones is spawned (3 for fire, 4 for collapse)
- [ ] Correct sensor list is attached
- [ ] Correct altitude and speed defaults are applied
- [ ] All priority tasks listed in the table are reflected in agent's plan
- [ ] Scenario constraint is respected (e.g., upwind position for fire, 200m standoff for industrial)

**Failure diagnosis:** If agent picks its own swarm type, the orchestrator handoff is wrong — agent should be _given_ the swarm config, not asked to choose.

### T4.4 — Agent 3 (Advisory, Ollama)
- [ ] Triggers on `agent_1_report_received` — verify by intercepting the event
- [ ] Triggers on `agent_2_findings_updated`
- [ ] Triggers on `world_event_fired`
- [ ] Triggers on `operator_query`
- [ ] 60s heartbeat triggers if no other trigger fires
- [ ] Output contains all six required sections: SITUATION SUMMARY, IMMEDIATE ACTIONS, EXCLUSION ZONES, RESOURCE REQUIREMENTS, RISK FLAGS, MONITORING
- [ ] Output updates when new agent data arrives — verify by injecting a second report

### T4.5 — Agent isolation
- [ ] Agent 1 cannot read Agent 2's conversation history
- [ ] Agent 2 cannot read Agent 1's reasoning (only Agent 1's reported output)
- [ ] Agent 3 receives reports, not raw conversation traces
- [ ] Test: inject a poison string into Agent 1's context and verify it never appears in Agent 2 or Agent 3 traces

**Acceptance:** All pass. Agent isolation failure is a contract violation, not a minor bug.

---

## TEST CATEGORY 5 — Orchestration & state machine

**Goal:** The LangGraph orchestrator transitions cleanly and survives chaos.

### T5.1 — State transitions
- [ ] `STANDBY → SURVEILLANCE_ACTIVE` on go signal
- [ ] `SURVEILLANCE_ACTIVE → SWARM_ACTIVE` on Agent 1 report
- [ ] `SWARM_ACTIVE → ADVISORY_ACTIVE` on Agent 2 findings
- [ ] `* → MULTI_INCIDENT` on second marker
- [ ] `* → EMERGENCY` on emergency abort signal
- [ ] `EMERGENCY` issues RTL to all active drones within 1 tick

### T5.2 — SQLite checkpointer
- [ ] After every state transition, checkpoint is written
- [ ] Kill orchestrator mid-flight; restart; state restored within 10 seconds (spec: 10s)
- [ ] Drones resume their last commanded action (or hold/RTL if context is unrecoverable — document which)

### T5.3 — Strict sub-key ownership
- [ ] Agent 1 only writes to `state.agent_1` (or whatever key was chosen)
- [ ] Agent 2 only writes to `state.agent_2`
- [ ] Agent 3 only writes to `state.agent_3`
- [ ] Concurrent writes from two agents to their own keys do not race or overwrite each other
- [ ] Test: fan out Agent 1 and Agent 2 simultaneously, verify both writes land

### T5.4 — IncidentManager
- [ ] First marker → creates incident with isolated Agent 1 + Agent 2 stack
- [ ] Second marker lower priority → queued
- [ ] Second marker higher priority → resources reassigned per spec's `assess_priority` logic
- [ ] Each incident has its own agent stack; Agent 3 is shared

**Acceptance:** All pass. State machine failures are the worst kind — they manifest as ghost drones and missing advisories.

---

## TEST CATEGORY 6 — Map rendering safety

**Goal:** The Mapbox concurrent-update glitch (rated CRITICAL in the spec's risk table) cannot happen.

### T6.1 — MapStateManager is the only writer
- [ ] Grep the codebase: no `map.addSource`, `map.addLayer`, `map.setData`, or equivalent direct Mapbox calls outside `map_state_manager.py` / `MapStateManager`
- [ ] Agents have no path to call the map directly
- [ ] Test by attempting an agent-side map write — must fail or be ignored

### T6.2 — 1-second batching
- [ ] Issue 10 rapid annotation writes from agents within 200ms
- [ ] MapStateManager batches and emits a single GeoJSON update at the next 1s tick
- [ ] No intermediate updates leak through

### T6.3 — Drone animation smoothness
- [ ] Drone moves visibly smooth on map (no teleporting)
- [ ] requestAnimationFrame lerp interpolates between telemetry ticks
- [ ] CSS heading rotation reflects current heading
- [ ] With 10 active drones, frame rate stays above 30 FPS in the browser

**Acceptance:** All pass. T6.1 is the keystone — if anything writes outside MapStateManager, the demo will glitch.

---

## TEST CATEGORY 7 — End-to-end happy path

**Goal:** A marker placed by the operator produces an advisory on screen, every single time.

### T7.1 — Fire scenario, full loop
- [ ] Operator drops fire marker on map
- [ ] Within ~2s, Agent 1 fixed-wing drone(s) take off
- [ ] Drone flies to marker, overflies, returns sensor data
- [ ] Agent 1 reports classification "fire" with confidence
- [ ] Orchestrator transitions to SWARM_ACTIVE
- [ ] Agent 2 spawns 3 thermal_rotary drones with correct sensors
- [ ] Specialist swarm establishes upwind position
- [ ] Agent 3 produces advisory with all 6 sections
- [ ] Advisory panel renders the output correctly
- [ ] Drones eventually RTL when commanded

### T7.2 — Second scenario, full loop
Pick one of: structural_collapse, flood, industrial_hazard, maritime_sar (whichever was built in Stage 5).
- [ ] Same checklist as T7.1, with the scenario-appropriate swarm config

### T7.3 — World event mid-flight
- [ ] During T7.1, trigger a world event (fire grows)
- [ ] Agent 1 flags area growth
- [ ] Agent 3 advisory updates within 1 trigger cycle
- [ ] Map reflects new perimeter

**Acceptance:** Run T7.1 three times in a row with cold starts. All three must succeed end-to-end without manual intervention.

---

## TEST CATEGORY 8 — Multi-incident

**Goal:** The system does not collapse under simultaneous markers (spec'd state: MULTI_INCIDENT).

### T8.1 — Two markers, sequential
- [ ] Place fire marker. Wait for SURVEILLANCE_ACTIVE.
- [ ] Place flood marker mid-surveillance.
- [ ] Orchestrator transitions to MULTI_INCIDENT
- [ ] IncidentManager spawns second isolated stack
- [ ] Both incidents progress independently
- [ ] Agent 3 receives reports from both and produces a single combined advisory (or per-incident — verify which the spec implies; if ambiguous, ask)

### T8.2 — Priority reassignment
- [ ] First marker is low severity, second is critical
- [ ] Per spec, `assess_priority` returns "higher" — resources are reassigned to the critical one
- [ ] Low severity incident is queued, not dropped

### T8.3 — No state bleed between incidents
- [ ] Incident A's drones do not appear in Incident B's telemetry payload
- [ ] Agent 1 instances for different incidents do not share context
- [ ] Verify by injecting a unique token per incident and confirming isolation

**Acceptance:** All pass. Spec lists "Multi-incident parallel stacks fully tested" as V2 — so for V1, T8.1 and T8.3 are the minimum bar; T8.2 is bonus but should at least not crash.

---

## TEST CATEGORY 9 — Failure mode fallbacks

**Goal:** Every mitigation listed in the spec's risk table actually works when its failure is induced.

### T9.1 — Mapbox concurrent update glitch (CRITICAL)
- [ ] Already covered by T6.1, T6.2 — verify fallback works: kill MapStateManager and confirm UI switches to Omium trace tab gracefully

### T9.2 — Drone animation teleport (CRITICAL)
- [ ] Already covered by T6.3 — verify fallback: artificially spawn 30 drones, confirm system reduces active count or degrades gracefully (no browser crash)

### T9.3 — LangGraph fan-out race (HIGH)
- [ ] Already covered by T5.3 — verify fallback: corrupt one agent's state key, confirm SQLite checkpointer restores within 10s

### T9.4 — Ollama slow on local hardware (MEDIUM)
- [ ] Add 30s latency to Ollama responses (sleep stub)
- [ ] Confirm cached last advisory is shown
- [ ] Confirm spinner appears
- [ ] Confirm rest of system stays responsive

### T9.5 — Omium SDK auth failure (LOW)
- [ ] Disable Omium real SDK auth
- [ ] Mock tracer takes over with structurally identical output
- [ ] Confirm console trace appears in terminal

**Acceptance:** All pass. Fallbacks aren't optional polish — they're load-bearing for the demo.

---

## FIX-UNTIL-GREEN PROTOCOL

When a test fails:

1. **Stop.** Do not proceed to the next test.
2. **Diagnose root cause.** Not the symptom. If a drone teleports, the cause is not "the icon jumped" — it's "telemetry tick rate doesn't match animation lerp window" or "MapStateManager bypassed."
3. **Check whether the fix violates `SPEC.md`.** If yes, STOP and ask. Do not silently re-architect.
4. **Apply the fix.** Make the smallest change that addresses the root cause.
5. **Update `HANDOVER.md`** with: symptom, root cause, fix, files changed.
6. **Re-run the failed test.** It must pass.
7. **Re-run all earlier tests in the same category.** No regressions allowed.
8. **Continue.**

If the same test fails twice with different fixes:
- Stop and surface the issue. The problem is upstream of where you're looking.
- Bring the user in. Do not enter a loop of guessing fixes.

---

## FINAL DELIVERABLE — SYSTEM_TEST_REPORT.md

After all 9 categories pass, generate `SYSTEM_TEST_REPORT.md` with:

```markdown
# ARIA v1 — System Test Report
**Date:** YYYY-MM-DD
**Result:** ✅ ALL PASS  /  ❌ FAILURES REMAIN

## Category-by-category results
- T1 Process lifecycle: PASS (with timings)
- T2 Data contracts: PASS
- T3 Drone kinematics: PASS
- T4 Agent reasoning: PASS
- T5 Orchestration: PASS
- T6 Map rendering: PASS
- T7 End-to-end: PASS (3/3 cold-start runs)
- T8 Multi-incident: PASS
- T9 Failure fallbacks: PASS

## Fixes applied during testing
(timestamped list — symptom → root cause → fix → files)

## Known limitations (acceptable for V1)
- (e.g., only 2 of 5 scenarios built, per spec)
- (e.g., predictive collapse modeling deferred to V2)

## Demo readiness
- [ ] README quickstart verified on clean machine
- [ ] Demo script written and timed
- [ ] Fallback recording made
- [ ] All risks in spec's risk table have working mitigations

## Sign-off
System meets ARIA v1 spec. Ready for demo.
```

The report is the final artifact. It is the proof the system works.

---

## RULES THAT OVERRIDE EVERYTHING ELSE

- **Never mark a test "passed with caveats."** Pass or fail, no middle ground.
- **Never delete a failing test to make CI green.** Fix the code.
- **Never modify `SPEC.md`** to match buggy behavior. Fix the code.
- **Never skip a test** because it "should obviously work." That's exactly when it doesn't.
- **If a fix requires a spec change**, STOP and ask the user. The spec is the contract.
