# ARIA v1 — CONTEXT

> **Read at the start of every session.** Update at the end.
> This file is what a fresh Claude Code instance needs to be productive immediately.
> Keep it dense. No fluff.

---

## What this project is (one line)

Multi-agent autonomous drone swarm simulation for disaster response — three Claude/Ollama agents control kinematic drones, identify incidents, deploy specialist swarms, and emit response plans to a Mapbox operator screen.

## Source of truth

`SPEC.md` — read-only. Never edit. If something seems wrong in the spec, surface it and ask, don't patch silently.

## Current stage

**Stage:** Stage 5 — Demo Polish
**Last verified working:** Stages 1-4 all checkpoints verified 2026-05-16:
  - Stage 1 (6 CPs): FastAPI, WebSocket, markers, frontend, GO signal, fly_to
  - Stage 2 (8 CPs): BaseAgent OODA-R, all tools, Agent 1 instantiation, tracer
  - Stage 3 (7 CPs): LangGraph orchestrator, classifier, IncidentManager, Agent 2
  - Stage 4 (10 CPs): Agent 3 Claude API, section validation, world events, heartbeat
**Next concrete task:** Stage 5 — Demo Polish (second scenario, multi-incident, demo script)

Update this block after every session.

---

## Operating rules (do not deviate)

1. **Opus planner first.** Enter plan mode before any non-trivial work. No code in plan mode.
2. **Stage gates are hard.** Each of the 5 stages ends with a confirmation checkpoint. Do not proceed without explicit user approval.
3. **V1 only.** The "V2 DEFERRED" section of the spec is off-limits. The single exception: the `DroneInterface` abstraction is built now to make V2 SITL swap clean.
4. **Parallel subagents for independent work** — scaffolding across directories, library research, isolated tests. Never parallelize work touching the same file or with sequential dependencies.
5. **Ask before inventing.** Anything not in `SPEC.md` (ports, secret handling, test framework choice, logging format, etc.) gets asked, not assumed.
6. **HANDOVER.md after every meaningful block.** Stage completion, blocker hit, decision made → append timestamped entry.

---

## Architectural decisions (locked, do not revisit)

These come straight from the spec. They are not up for debate during the build.

- **Kinematic drone model in V1.** No SITL, no JSBSim. `DroneInterface` abstract base class is the seam SITL will swap into in V2.
- **Orchestrator is NOT an LLM.** It's a deterministic LangGraph state machine + SQLite checkpointer.
- **Agent 1 + 2 use Claude API** (`claude-sonnet-4-20250514`). Agent 3 uses **local Ollama** (`llama3.1:8b`).
- **Agent 2 does NOT choose its swarm type.** The decision table `SWARM_CAPABILITIES` in code maps marker type → swarm config. Agent 2 reasons within the chosen config.
- **MapStateManager is the single writer to Mapbox.** Agents never touch the map directly. All GeoJSON batched on a 1s interval.
- **Drone animation:** requestAnimationFrame lerp 500ms + CSS heading rotation. No teleporting.
- **LangGraph fan-out safety:** Each agent writes only to `state.{its_key}`. Strict sub-key ownership.
- **Information sharing is a contract.** See `SHARED_TO_AGENTS`, `HIDDEN_FROM_AGENTS`, `SHARED_TO_SIMULATION` in spec. Agents cannot read each other's reasoning. Agents cannot see world seed, future events, or full zone graph.

---

## Decisions made during the build (append here)

Format: `YYYY-MM-DD — decision — rationale`

- 2026-05-15 — Python 3.11, Node 22 LTS, pytest, structlog, .env+python-dotenv — user choice at session start
- 2026-05-15 — FastAPI port 8000, Vite port 5173 — standard defaults, user confirmed
- 2026-05-15 — GO signal flow: operator sends full context (area+polygon+disaster_type), orchestrator strips to coordinates-only for Agent 1 — per CHANGE 1 spec
- 2026-05-15 — Sensor overlay uses ray-casting point-in-polygon (not distance-to-center) — per CHANGE 3 spec
- 2026-05-15 — Agent 1 survey pattern: expanding circles at 50m, 100m, 150m with 8 orbit points each — per CHANGE 2 spec
- 2026-05-16 — Agent 3 uses Claude API instead of Ollama — user decision, eliminates local model dependency
- 2026-05-16 — All agents use claude-sonnet-4-20250514 — user confirmed model choice
- 2026-05-16 — Agent 1 survey is LLM-driven (not hardcoded) — LLM decides tool call sequence via OODA-R loop

---

## Gotchas / things that bit us (append here)

Format: `YYYY-MM-DD — symptom — root cause — fix`

- 2026-05-15 — `python` command not found — macOS uses `python3`; `pip install` blocked by PEP 668 — use `setup.sh` to create venv, then `source venv/bin/activate` before all backend commands
- 2026-05-15 — active_agent1 garbage collected immediately — asyncio task + no reference kept the survey loop alive only briefly — fixed by storing reference in module-level `active_agent1` global

---

## Conventions established

- **File layout:** matches spec exactly. Do not invent new directories.
- **Python version:** 3.13.4 (venv; CONTEXT.md previously said 3.11 — actual venv is 3.13.4)
- **Node version:** 22 LTS
- **Test framework:** pytest + pytest-asyncio
- **Logging:** structlog (ConsoleRenderer in dev, JSON in prod)
- **Secrets:** .env + python-dotenv (ANTHROPIC_API_KEY, MAPBOX_TOKEN, VITE_MAPBOX_TOKEN)

---

## Running the system

*(Fill in once Stage 1 is up. Expected sections: how to start the backend, how to start the frontend, how to run Ollama, where the operator UI lives, how to trigger a scenario.)*

---

## Key files at a glance

- `SPEC.md` — the build spec (read-only)
- `CONTEXT.md` — this file
- `HANDOVER.md` — running log
- `main.py` — entry point (Stage 1+)
- `config.yaml` — ports, model names, scenario paths (Stage 1+)
- `sim/drone_interface.py` — the V1→V2 seam
- `orchestrator/orchestrator.py` — LangGraph state machine
- `sim_layer/map_state_manager.py` — single Mapbox writer
