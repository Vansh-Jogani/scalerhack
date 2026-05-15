# CLAUDE.md — Project Instructions for Claude Code

> Claude Code auto-loads this file every session. Keep it short and operational.

## Project: ARIA v1

Multi-agent autonomous drone swarm simulation. Spec is in `SPEC.md` (read-only).

## Session start checklist

Run in order at the start of every session:

1. Read `CONTEXT.md` — the persistent context file.
2. Read the latest 5 entries of `HANDOVER.md` — the running log.
3. `git status` and `git log --oneline -10` — see where the tree is.
4. Confirm current stage (1–5) and the next concrete task.
5. Only then begin work.

## Operating mode

- **Plan mode (Opus) before any non-trivial work.** No code in plan mode. Present plan → wait for approval → execute.
- **Parallel subagents** for independent work (scaffolding different directories, library research, isolated tests). Never for sequential or same-file work.
- **Stage gates are hard.** After every stage, stop and wait for explicit "proceed" before starting the next.
- **V1 only.** The "V2 DEFERRED" list in `SPEC.md` is off-limits — except the `DroneInterface` abstraction, which is built now as the V2 seam.

## When to update files

- After every meaningful block (stage done, blocker hit, decision made): append a timestamped entry to `HANDOVER.md` (newest on top).
- At session end OR when the user says "checkpoint": update `CONTEXT.md` (current stage, last verified working, next task, any new decisions/gotchas/conventions).
- Never edit `SPEC.md`.

## Asking vs deciding

If something is not in `SPEC.md`, **ask first**:
- Port numbers not specified
- Secret/auth handling
- Logging format
- Test framework
- Anything that becomes a load-bearing convention

If something is in `SPEC.md`, **follow it** — do not "improve" it without surfacing the change first.

## Stage 1 acceptance (6 checkpoints — all required)

1. FastAPI running, WebSocket confirmed
2. World state with one marker
3. DroneModel tick loop — one drone position updating
4. One drone icon moving on Mapbox map
5. `base_agent.py` observe/reason/act loop working
6. One tool call (`fly_to`) executing against DroneModel

Demonstrate each one running. Then stop.
