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

**Stage:** Not started — Stage 1 pending
**Last verified working:** N/A
**Next concrete task:** Produce Stage 1 plan in Opus plan mode

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

- *(none yet)*

---

## Gotchas / things that bit us (append here)

Format: `YYYY-MM-DD — symptom — root cause — fix`

- *(none yet)*

---

## Conventions established

- **File layout:** matches spec exactly. Do not invent new directories.
- **Python version:** *(decide in Stage 1, then lock here)*
- **Node version:** *(decide in Stage 1, then lock here)*
- **Test framework:** *(decide in Stage 1, then lock here)*
- **Logging:** *(decide in Stage 1, then lock here)*
- **Secrets:** *(decide in Stage 1, then lock here — likely .env + python-dotenv)*

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
