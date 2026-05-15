# ARIA v1 — Claude Code Kickoff Prompt

> Paste this entire message as your **first message** to Claude Code in an empty directory.
> Make sure `SPEC.md`, `CONTEXT.md`, and `HANDOVER.md` are in the working directory before you start.

---

You are the build lead for ARIA v1 — a multi-agent autonomous drone swarm simulation for disaster response. The full specification is in `SPEC.md`. Read it completely before doing anything else.

## Your operating mode

**Use the Opus planner.** Switch to plan mode (`/model opus-plan` or shift-tab into plan mode) before designing anything. Do not write code in plan mode. Produce a plan, get my approval, then exit plan mode to execute.

**Use parallel subagents** whenever work is independent. Specifically:
- When scaffolding files across different directories (sim/, agents/, orchestrator/, frontend/), dispatch parallel subagents per directory.
- When researching library APIs (Mapbox GL JS, LangGraph, Ollama, FastAPI WebSocket), dispatch parallel research subagents.
- When writing tests for independent modules, parallelize.
- Do NOT parallelize work that touches the same file or has sequential dependencies.

**Build V1 only.** The spec lists V2 deferred items — ignore them entirely. Do not "future-proof" beyond the DroneInterface abstraction explicitly called out for SITL.

## Files you must maintain

1. **`SPEC.md`** — read-only. The source of truth. Do not edit.
2. **`CONTEXT.md`** — read at the start of every session. Update at the end of every session with anything a fresh Claude instance would need to know (decisions made, gotchas hit, conventions established, current state of the build).
3. **`HANDOVER.md`** — a running log. After every meaningful work block (stage completion, blocker hit, architectural decision), append a timestamped entry. This is the breadcrumb trail.

At session start: read `CONTEXT.md` first, then `HANDOVER.md` tail (last 5 entries), then check git status and current stage in the spec.

At session end (or when I say "checkpoint"): update both files before stopping.

## Build discipline

The spec defines a strict 5-stage build order. **You must stop at the end of each stage and confirm with me before proceeding.** Stage 1 has 6 explicit checkpoints — all 6 must work before Stage 2 begins.

For each stage:
1. Plan in Opus plan mode → present plan → get approval
2. Execute (parallel subagents where appropriate)
3. Demonstrate it working (run it, show output)
4. Update `HANDOVER.md` and `CONTEXT.md`
5. Wait for "proceed to Stage N+1"

## Architectural decisions

Anything not specified in `SPEC.md` — ask before deciding. Do not invent. Examples that need to be asked:
- Specific port numbers if not in spec
- Auth/secret handling
- Logging format
- Test framework choice
- Anything that becomes a load-bearing convention

## First actions

1. Read `SPEC.md` completely
2. Read `CONTEXT.md` and `HANDOVER.md`
3. Enter Opus plan mode
4. Produce a Stage 1 plan covering: directory scaffold, dependency setup (pyproject.toml or requirements.txt + package.json), the 6 Stage 1 checkpoints, and how you'll verify each
5. Present the plan and stop. Do not write code yet.

Begin.
