# ARIA v1 — Prompt & Comms Layer Integration

> **Context:** The prompt registry, tool schemas, handoff messages, and event bus have been built on a separate machine. The main ARIA system (sim, agents, orchestrator, frontend) was built in parallel on this machine. Both are ready. Now they merge.
>
> **When to run:** After receiving the `prompts-comms-package/` (the 4 deliverables) and confirming the main system runs Stage 1–4 without it.

---

## KICKOFF BLOCK (paste to Claude Code)

```
You are integrating the prompt & comms layer into the main ARIA v1 system.

The prompt+comms package was built on a separate machine and lives in
./prompts-comms-package/ (or wherever the user placed it). The main system
is already built and was running with inline prompts and untyped dicts
between agents. Your job is to merge the package in cleanly, verify nothing
broke, then run the full integration test suite.

Read INTEGRATION.md completely before doing anything.

Operating rules:
1. Enter Opus plan mode. Read SPEC.md, CONTEXT.md, last 5 HANDOVER.md
   entries, then INTEGRATION.md. Inspect the incoming package and the
   current state of agents/, orchestrator/, prompts/ (if any).
2. Produce a 5-phase integration plan (see below). Present it. Wait for
   approval. No code in plan mode.
3. After approval: execute phase by phase. Stop at each phase boundary
   to confirm the system still boots and Stage 1 smoke test still passes.
4. Use parallel subagents for independent migration work (one agent file
   per subagent, since each is isolated). Never parallelize work touching
   the orchestrator file or the same agent file.
5. Every phase ends with: HANDOVER.md entry + a brief verification run.
6. If you find a real conflict between the package and the existing system
   that requires a design decision — STOP and ask. Do not silently
   reconcile by overwriting either side.

Begin: read context files, inspect both sides, produce the integration plan.
```

---

## WHAT THE PACKAGE CONTAINS

The package built on the other machine includes:

```
prompts-comms-package/
├── prompts/
│   ├── registry.py
│   ├── agent1_surveillance.md
│   ├── agent2_specialist.md
│   ├── agent3_advisory.md
│   └── _shared/
│       ├── output_contracts.md
│       ├── safety_rules.md
│       └── notes.md                     ← contains maritime_sar TODO
│
├── agents/
│   ├── tools/
│   │   └── schemas.py                   ← Pydantic tool schemas + to_claude_tool_dict()
│   └── messages.py                      ← SurveillanceReport, IncidentBriefing, WorldEvent
│
├── orchestrator/
│   └── event_bus.py                     ← pub/sub with 500ms coalescing
│
├── tests/
│   ├── test_prompt_registry.py
│   ├── test_tool_schemas.py
│   ├── test_handoff_messages.py
│   ├── test_event_bus.py
│   └── test_agent_isolation.py          ← poison-string test
│
└── PACKAGE_NOTES.md                     ← assumptions made, version hashes, etc.
```

**Read `PACKAGE_NOTES.md` first** — it describes any decisions made during the package build that may affect integration.

---

## WHAT THE EXISTING SYSTEM LOOKS LIKE (pre-integration)

Before the package lands, the main system has:

- `agents/agent1_surveillance.py` with `AGENT_1_SYSTEM_PROMPT = """..."""` inline
- `agents/agent3_advisory.py` with `AGENT_3_SYSTEM_PROMPT = """..."""` inline
- `agents/agent2_specialist.py` with some improvised prompt (spec had none)
- Hand-written tool dicts inline in each agent file
- Free-text dicts between Agent 1 → Agent 2 → Agent 3
- Either polling or callbacks for Agent 3 triggers (improvised — spec didn't specify)

The integration replaces all of these with the package's typed equivalents.

---

## THE 5-PHASE INTEGRATION PLAN

### Phase 0 — Pre-flight (read-only)

- [ ] Confirm Stage 1 smoke test still passes with current code (baseline before changes)
- [ ] Inspect package: read `PACKAGE_NOTES.md`, list files, confirm all 4 deliverables present
- [ ] Diff the inline prompts in existing agent files vs the markdown prompts in the package — flag any meaningful drift
- [ ] Run the package's own test suite (`pytest prompts-comms-package/tests/`) — all should pass standalone

**Stop point:** if pre-flight finds drift between inline and package prompts, ask which version is authoritative.

---

### Phase 1 — Drop in package files (no wiring yet)

Files are placed but nothing in the existing system uses them yet. System still runs on the old code.

- [ ] Copy `prompts/` → project root
- [ ] Copy `agents/messages.py`, `agents/tools/schemas.py` → into existing `agents/` (do NOT overwrite `agents/agent*.py`)
- [ ] Copy `orchestrator/event_bus.py` → into existing `orchestrator/` (do NOT overwrite `orchestrator/orchestrator.py`)
- [ ] Copy `tests/` contents → into project's existing test directory
- [ ] `pytest` — package tests pass, existing tests still pass

**Verification:** `python main.py` boots. Stage 1 smoke test passes. Nothing has changed at runtime yet.

**HANDOVER.md entry. Stop point.**

---

### Phase 2 — Migrate prompts to registry

The smallest change. Swap inline prompt strings for `load_prompt()` calls.

- [ ] `agents/agent1_surveillance.py`: replace inline prompt with `prompt, v = load_prompt("agent1_surveillance")`
- [ ] `agents/agent2_specialist.py`: same — and remove the improvised prompt entirely
- [ ] `agents/agent3_advisory.py`: same
- [ ] Log the version hash at agent startup
- [ ] Grep verifies: no triple-quoted prompt strings remain in `agents/*.py`

**Verification:** run an Agent 1 invocation. Agent reasons normally. Version hash appears in logs.

**Parallel subagents OK here** — one per agent file, since they're isolated.

**HANDOVER.md entry. Stop point.**

---

### Phase 3 — Migrate tool schemas

Replace hand-written tool dicts with `Schema.to_claude_tool_dict()` calls and add input validation at the tool dispatcher.

- [ ] Agent 1: tools list assembled from `FlyTo`, `LoiterOver`, `GetSensorReading`, `ReportClassification`, `RequestDetailedPass`
- [ ] Agent 2: tools list assembled from batch swarm command schema + `UpdateZoneClassification`, `MarkSurvivor`, `MarkHazard`, `ReportSwarmFindings`
- [ ] Agent 3: per the resolved decision, uses tool-use for advisory schema enforcement — wire the `IssueAdvisory` tool
- [ ] Tool dispatcher validates inputs through Pydantic before executing against the simulation
- [ ] Malformed tool calls return a typed error to the agent (not a crash)

**Verification:** run an Agent 1 invocation that calls `fly_to`. Inject a malformed call (missing `lat`) — agent receives a validation error, world state unchanged.

**HANDOVER.md entry. Stop point.**

---

### Phase 4 — Migrate handoffs to typed messages

This is the highest-impact phase. The orchestrator changes shape.

- [ ] `orchestrator/orchestrator.py`: when Agent 1 finishes, construct a `SurveillanceReport` Pydantic model. Validation fails fast at the boundary if anything's missing.
- [ ] Pass `SurveillanceReport.model_dump_json()` to Agent 2 as input payload — Agent 2 does not see Agent 1's tool-call history.
- [ ] When Agent 2 finishes, combine into `IncidentBriefing`. Pass to Agent 3 the same way.
- [ ] Remove any free-text dicts between agents (grep `{"type":` etc. — should be zero hits in the handoff path)

**Verification:** end-to-end run — marker → A1 → A2 → A3. Confirm each handoff payload is a valid Pydantic model. Run the poison-string isolation test from the package.

**HANDOVER.md entry. Stop point.**

---

### Phase 5 — Wire event bus

Replace whatever Agent 3 trigger mechanism exists with the event bus.

- [ ] Orchestrator publishes: `agent_1_report_received`, `agent_2_findings_updated`
- [ ] World state publishes: `world_event_fired`
- [ ] Operator API publishes: `operator_query`
- [ ] Background task: 60s heartbeat publisher
- [ ] Agent 3 subscribes to all five trigger types
- [ ] 500ms coalescing verified: rapid-fire 3 publishes within 500ms → Agent 3 runs once with latest state

**Verification:** trigger a world event (fire grows) during an active incident. Agent 3 advisory updates. Logs show coalescing working.

**HANDOVER.md entry. Stop point.**

---

## INTEGRATION TEST SUITE

Once all 5 phases are complete, run this — it's the gate before declaring integration done.

### IT-1 — System still boots cleanly
- [ ] `python main.py` starts, all services up, Stage 1 smoke test passes

### IT-2 — Prompt versions in logs
- [ ] Each agent startup logs its prompt name + version hash
- [ ] Changing a prompt file changes the version hash on next reload
- [ ] No prompt is inlined in any `.py` file (`grep -rn 'You are ARIA' --include='*.py'` returns zero results outside `prompts/`)

### IT-3 — Tool schema enforcement
- [ ] Every tool an agent calls is validated by its Pydantic schema
- [ ] Malformed tool call → typed error returned to agent, not a crash
- [ ] Tool schemas match what's documented in the package's `PACKAGE_NOTES.md`

### IT-4 — Typed handoffs work end-to-end
- [ ] Fire scenario: marker → Agent 1 → `SurveillanceReport` validated → Agent 2 → `IncidentBriefing` validated → Agent 3 → advisory rendered on UI
- [ ] Inject a broken handoff (manually emit a `SurveillanceReport` missing a required field) → orchestrator rejects it cleanly, system does not silently continue with bad data
- [ ] Run end-to-end three times cold-start. All three succeed.

### IT-5 — Agent isolation holds
- [ ] Run the poison-string test from `test_agent_isolation.py`
- [ ] Inject a unique sentinel string into Agent 1's tool-call results during an active run
- [ ] Verify the string does not appear in Agent 2's context, Agent 3's context, or any logs except Agent 1's own trace

### IT-6 — Event bus + coalescing
- [ ] Publish 3 trigger events within 500ms → Agent 3 runs exactly once with the latest state
- [ ] Publish 2 trigger events 700ms apart → Agent 3 runs twice
- [ ] Kill Agent 3 mid-trigger → next trigger still fires correctly after restart
- [ ] Heartbeat fires after 60s of silence; does NOT fire if any other trigger fired in the last 60s

### IT-7 — Stage gates re-verified
Re-run the Stage 1–4 acceptance checkpoints from `SPEC.md`. All must still pass. The integration must not have regressed any earlier stage.

### IT-8 — Multi-incident smoke
- [ ] Place 2 markers near-simultaneously
- [ ] IncidentManager spawns isolated stacks
- [ ] Each incident has its own `SurveillanceReport` and `IncidentBriefing`
- [ ] Agent 3 receives both briefings correctly (per the decision in the package — confirm whether merged or separate)
- [ ] No state bleed between incidents (incident_id present and correct on every payload)

### IT-9 — Failure recovery
- [ ] Kill orchestrator mid-incident → SQLite checkpointer restores within 10s → typed messages still serialize/deserialize correctly across the restart
- [ ] Kill event bus subscriber (Agent 3 runner) → restart → subscriptions re-established → next trigger fires correctly

---

## ACCEPTANCE

Integration is complete when:

- [ ] All 5 phases done
- [ ] All 9 integration tests (IT-1 through IT-9) pass
- [ ] No inline prompts remain anywhere in agent code
- [ ] No free-text dicts remain in inter-agent handoff paths
- [ ] All Stage 1–4 acceptance criteria from `SPEC.md` still pass
- [ ] `HANDOVER.md` has entries for all 5 phases + integration test results
- [ ] `CONTEXT.md` updated with: prompt registry conventions, message schema conventions, event bus conventions, the location of `PACKAGE_NOTES.md`
- [ ] `INTEGRATION_REPORT.md` produced — final summary with timings, fixes applied, and any deviations from the plan

---

## FIX-UNTIL-GREEN PROTOCOL (applies to all phases)

When something fails during integration:

1. **Stop the current phase.** Do not skip ahead.
2. **Diagnose root cause** — not the symptom. If `SurveillanceReport` validation fails, the cause is in how Agent 1 produces its report, not in the schema.
3. **Determine which side is right** — the package (which is the new source of truth for prompt/comms) or the existing system (which is the source of truth for sim/agent behavior). The package wins for prompts, tool schemas, messages, and event bus. The existing system wins for sim/agent business logic and the spec'd flow.
4. **If both sides disagree on something the spec covers** — the spec wins. Bring it to the user.
5. **Fix the smallest thing that addresses the root cause.** Resist re-architecting.
6. **Re-run the verification for the current phase.** Then re-run prior phases' verifications. No regressions.
7. **HANDOVER.md entry** with: symptom, root cause, fix, files touched.

If a fix attempt fails twice — stop and ask. Two failed attempts means you're guessing.

---

## FINAL DELIVERABLE — INTEGRATION_REPORT.md

```markdown
# ARIA v1 — Prompt & Comms Integration Report
**Date:** YYYY-MM-DD
**Result:** ✅ INTEGRATED  /  ❌ FAILURES REMAIN

## Phase results
- Phase 0 Pre-flight: PASS
- Phase 1 Drop files: PASS
- Phase 2 Prompt registry: PASS
- Phase 3 Tool schemas: PASS
- Phase 4 Typed handoffs: PASS
- Phase 5 Event bus: PASS

## Integration tests
- IT-1 through IT-9: PASS

## Fixes applied during integration
(timestamped list — symptom → root cause → fix → files)

## Drift between package and existing system (if any)
(documented — what was the conflict, how was it resolved)

## Prompt version hashes at integration time
- agent1_surveillance: <hash>
- agent2_specialist: <hash>
- agent3_advisory: <hash>
- output_contracts: <hash>
- safety_rules: <hash>

## Sign-off
Integration complete. System runs ARIA v1 spec with structured prompts and typed comms.
Ready for full system test (FULL_SYSTEM_TEST.md).
```

---

## RULES THAT OVERRIDE EVERYTHING ELSE

- **Never silently overwrite** existing agent business logic with package content. The package replaces the prompt/comms layer only.
- **Never modify `SPEC.md`** to match either side. Spec is the contract.
- **Never skip a phase verification** to make later phases work. If Phase 2 verification fails, fix Phase 2 before touching Phase 3.
- **Never declare integration "done with caveats."** All 9 integration tests pass, or it's not done.
- **The next step after this integration completes** is `FULL_SYSTEM_TEST.md`. Do not run it before integration is signed off — it will fail noisily and waste a session.
