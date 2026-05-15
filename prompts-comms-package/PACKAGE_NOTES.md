# ARIA v1 — Prompt & Comms Package Notes

**Build date:** 2026-05-16
**Build machine:** fedora (Linux 7.0.4-200.fc44.x86_64)
**Python version:** 3.14.4 (CPython, GCC 16.0.1)
**Pydantic version:** 2.13.4
**pytest version:** 9.0.3

Read this before running INTEGRATION.md.

---

## Content hashes (SHA-256, first 12 chars)

These are content hashes of the resolved files (includes expanded). The
integration machine should recompute and verify these match.

| File | SHA-256 (12 chars) |
|---|---|
| `prompts/agent1_surveillance.md` | `4fb41c898868` |
| `prompts/agent2_specialist.md` | `d16b6c0e08d4` |
| `prompts/agent3_advisory.md` | `ebf979527e70` |
| `prompts/_shared/safety_rules.md` | `e206bfb33141` |
| `prompts/_shared/output_contracts.md` | `2c825efdf766` |
| `prompts/_shared/notes.md` | `af2002969df9` |
| `prompts/registry.py` | `3b7771c51c6e` |
| `agents/tools/schemas.py` | `c1517da63f6b` |
| `agents/messages.py` | `9a48941533cd` |
| `orchestrator/event_bus.py` | `5b769c9e4c82` |

**Note:** `load_prompt()` computes a hash of the *resolved* text (after includes
are expanded). The hash logged at agent startup will differ from the raw file hash
above if an include file changes. Both are SHA-256 prefixed to 8 chars.

---

## Decisions made during the build

### 1. Agent 3 — Claude API with tool use (not Ollama)

**Decision:** Agent 3 was migrated from Ollama to Claude API. Advisory schema
enforcement uses `tool_choice={"type": "tool", "name": "issue_advisory"}` —
Claude is forced to call the tool, making output schema validation automatic.

**Rationale:** User explicitly requested this. Prompt-only JSON enforcement
is fragile on edge cases; tool-use guarantees the schema is always valid.

**Integration impact:** `agents/agent3_advisory.py` on the main PC uses Ollama.
Phase 3 of INTEGRATION.md replaces it with the Claude API variant. The
`ANTHROPIC_API_KEY` must be set for Agent 3. Ollama is no longer needed for
Agent 3 (it may still be used for other purposes on the main PC).

---

### 2. Agent 2 swarm control — batch command

**Decision:** Agent 2 uses `deploy_swarm(positions=[{drone_id, lat, lon, alt}])`
to move all swarm drones in one call, not separate `fly_to` calls per drone.

**Rationale:** User chose this. Fewer tool calls per reasoning step; cleaner
for swarm coordination where all positions are decided together.

**Integration impact:** The main PC's Agent 2 likely uses `fly_to` per drone.
Phase 3 must replace the Agent 2 tool list with `AGENT_2_TOOLS` which includes
`deploy_swarm` instead of individual `fly_to`. The `deploy_swarm` handler
(in `agent2_specialist.py`) iterates positions and calls `world_state.command_drone`
for each — no DroneModel changes required.

---

### 3. Agent 2 system prompt — generic template, maritime_sar deferred

**Decision:** A single generic `agent2_specialist.md` template is used for all
5 incident types. Template variables (`{{swarm_type}}`, `{{drone_count}}`, etc.)
are filled at runtime from `SWARM_CAPABILITIES[classification]`.

**Maritime SAR carve-out:** The generic zone-classification protocol does not map
well to maritime SAR's moving-target search patterns. A type-specific override
(`agent2_maritime_sar.md`) is flagged as a Stage 5 TODO. See
`prompts/_shared/notes.md` for full details and recommended implementation path.

**Integration impact:** None for Stages 1–4. Stage 5 will need the override.

---

### 4. Event bus coalescing window

**Decision:** 500ms coalesce window (constructor default).

**Rationale:** Starting point from the spec. Tunable via `EventBus(coalesce_window_s=X)`.
If Agent 3 latency is high on the main PC hardware, increase to 1000ms.

**Integration impact:** Wire `EventBus` into `orchestrator.py` during Phase 5.
The bus is not yet wired — `orchestrator.py` still calls `agent3.on_trigger()`
directly. Phase 5 replaces that direct call with `bus.publish(...)`.

---

### 5. Prompt version hashing — content hash, not git SHA

**Decision:** Prompt version hashes are SHA-256 of the resolved prompt text
(after `{{include:}}` directives are expanded), truncated to 8 hex chars.

**Rationale:** Content hash changes whenever the prompt changes, even mid-session
without a commit. Git SHA only changes on commit — too coarse for dev iteration.

**Integration impact:** Each agent logs `prompt_version_hash` at startup and on
every LLM call. The hash in logs identifies the exact prompt text in use. If
a prompt is edited and the process restarted, the hash changes automatically.

---

### 6. Agent isolation enforcement

**How it works:** Each agent gets only a typed Pydantic model as input, not the
previous agent's `messages[]` array or tool-call history.

- Agent 2 receives `SurveillanceReport` (structured fields only, no Agent 1 context)
- Agent 3 receives `IncidentBriefing` (structured reports only, no Agent 1 or 2 context)

The poison-string test in `tests/test_agent_isolation.py` verifies this contract.

---

## Deviations from PROMPT_COMMS_BUILD.md

| Spec item | What was done | Approved |
|---|---|---|
| Agent 3 uses local Ollama | Replaced with Claude API + tool use | Yes — user requested |
| Agent 2 per-drone fly_to | Replaced with batch deploy_swarm | Yes — user chose this option |
| Agent 2 prompt: "draft first for review" | Draft presented inline, approved, then built | Yes |
| Tool schema fidelity: "clean agent-facing, translate at boundary" | Implemented — schemas.py is the agent-facing API; handlers translate to world_state calls | Per spec recommendation |
| Coalescing window: "500ms as starting point" | 500ms used, tunable via constructor | Per spec recommendation |
| prompt_version_hash: "content-hash vs git-SHA" | Content hash chosen | Per spec recommendation + user confirmation |

---

## Test results

**Suite:** `tests/` (5 files, 77 tests)
**Result:** 77 passed, 0 failed
**Runtime:** 1.94s
**Python:** 3.14.4
**pytest:** 9.0.3

Test file breakdown:
- `test_prompt_registry.py` — 15 tests (load, cache, includes, fill_template, list)
- `test_tool_schemas.py` — 27 tests (structure, boundary enforcement, validation)
- `test_handoff_messages.py` — 16 tests (round-trip, rejection)
- `test_event_bus.py` — 8 tests (coalescing, heartbeat, error isolation)
- `test_agent_isolation.py` — 5 tests (poison-string, incident_id tracing)

---

## Required on the integration machine

- Python 3.11+ (built on 3.14.4 — no version-specific features used)
- `pydantic >= 2.0`
- `anthropic` SDK (for Agent 3 — Claude API)
- `pytest`, `pytest-asyncio` (for running the test suite)
- `ANTHROPIC_API_KEY` env var set (Agent 3 live calls)

Ollama is **not** required for Agent 3 after integration.
