# ARIA v1 — Prompt & Comms Integration Report
**Date:** 2026-05-16
**Result:** INTEGRATED

---

## Phase results

| Phase | Description | Result |
|---|---|---|
| Phase 0 Pre-flight | Read all context files, inspected both sides, verified 4 deliverables | PASS |
| Phase 1 Drop files | Package tests copied to tests/ — 138/138 pass | PASS |
| Phase 2 Prompt registry | Already complete — all agents use load_prompt() | PASS |
| Phase 3 Tool schemas | Already complete — all agents use Pydantic schemas | PASS |
| Phase 4 Typed handoffs | SurveillanceReport, SwarmFindings, IncidentBriefing wired through orchestrator | PASS |
| Phase 5 Event bus | EventBus wired with all 5 trigger types, coalescing verified | PASS |

---

## Integration tests

| Test | Description | Result |
|---|---|---|
| IT-1 System boots | python main.py imports clean, orchestrator init OK | PASS |
| IT-2 Prompt versions in logs | version_hash logged on every LLM call; no inline prompts in .py | PASS |
| IT-3 Tool schema enforcement | Pydantic validates all tool inputs; malformed call → typed error | PASS |
| IT-4 Typed handoffs e2e | Verified without live API: boundary validates, rejects malformed, briefing built correctly | PASS (without live LLM — needs ANTHROPIC_API_KEY for full advisory render) |
| IT-5 Agent isolation | pytest tests/test_agent_isolation.py — all 5 pass | PASS |
| IT-6 Event bus + coalescing | 3 events <500ms → 1 dispatch; 2 events 700ms apart → 2 dispatches; heartbeat after silence | PASS |
| IT-7 Stage gates | 138 tests pass including all original Stage 1 tests | PASS |
| IT-8 Multi-incident | IncidentBriefing carries incident_id on all payloads | PASS (structural) |
| IT-9 Failure recovery | ValidationError caught cleanly, system continues; bus error isolation confirmed | PASS |

---

## Fixes applied during integration

### 2026-05-16 — `prompt_version_hash` injection
**Symptom:** `SurveillanceReport` and `SwarmFindings` require `prompt_version_hash` but the LLM tool call (`block.input`) does not include it.
**Root cause:** The field was designed for behavioral correlation but no injection point was specified between the package and main system.
**Fix:** Each agent injects its own `self._prompt["version_hash"]` at the call site before dispatching to the handler. Agent 1 injects in `_classify()` when tool is `report_classification`. Agent 2 injects in `_handle_report_findings()`.
**Files:** `agents/agent1_surveillance.py`, `agents/agent2_specialist.py`

### 2026-05-16 — `latest_briefing` update timing
**Symptom:** `latest_briefing.trigger_type` still showed `agent_1_report_received` after `receive_agent2_report` was called.
**Root cause:** `_run_advisory` was async (fire-and-forget task) so `self.latest_briefing` wasn't updated before callers could read it.
**Fix:** Build `IncidentBriefing` and assign `self.latest_briefing` synchronously in `receive_agent2_report`. Only the bus publish is deferred to a task.
**Files:** `orchestrator/orchestrator.py`

### 2026-05-16 — config.yaml stale Ollama keys
**Symptom:** `models.agent3_endpoint` and `models.agent3_model: llama3.1:8b` were stale — Agent 3 was migrated to Claude API.
**Fix:** Removed stale keys, added `models.agent3: "claude-sonnet-4-20250514"`.
**Files:** `config.yaml`

---

## Drift between package and existing system

None significant. All 4 deliverable files (prompts, messages, schemas, event_bus) were byte-for-byte identical between `prompts-comms-package/` and the main system. Phases 1–3 were already complete.

The only cross-side gap was `prompt_version_hash` injection (documented above). Both sides agreed on the field — only the injection point was missing.

---

## Prompt version hashes at integration time

| File | SHA-256 (8 chars) — resolved text |
|---|---|
| `prompts/agent1_surveillance.md` | `ec1461ee` |
| `prompts/agent2_specialist.md` | `50d7b7cb` |
| `prompts/agent3_advisory.md` | `52e6d390` |
| `prompts/_shared/output_contracts.md` | `2c825efd` |
| `prompts/_shared/safety_rules.md` | `e206bfb3` |

Note: `agent2_specialist` hash differs from `PACKAGE_NOTES.md` (`d16b6c0e`) because `fill_template()` is called at runtime — the registry hash is of the raw template text, which matches. The runtime-filled hash (`50d7b7cb`) reflects the `fire` SWARM_CAPABILITIES fill used during this test.

---

## Sign-off

Integration complete. System runs ARIA v1 spec with structured prompts and typed comms.

- No inline prompts remain in any `agents/*.py`
- No free-text dicts remain in inter-agent handoff paths
- All 138 tests pass (61 original Stage 1 + 77 package)
- EventBus coalescing and heartbeat verified
- Boundary validation rejects malformed reports cleanly

Ready for full system test (`FULL_SYSTEM_TEST.md`) once `ANTHROPIC_API_KEY` is set.
