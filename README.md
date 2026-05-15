# ARIA v1 — Claude Code Setup Bundle

This bundle gives Claude Code everything it needs to build ARIA v1 with stage discipline, planning rigor, and session continuity.

## What's in here

| File | Purpose | Editable by Claude? |
|---|---|---|
| `SPEC.md` | Full build specification — source of truth | **No** |
| `CLAUDE.md` | Project instructions auto-loaded by Claude Code every session | Rarely (only if rules change) |
| `CONTEXT.md` | Persistent context across sessions — read at session start, updated at session end | Yes — every session end |
| `HANDOVER.md` | Append-only running log — newest entries on top | Yes — after every meaningful block |
| `KICKOFF_PROMPT.md` | The first message you paste into Claude Code | N/A — for you |

## How to use it

1. Create a fresh empty directory for the project.
2. Copy `SPEC.md`, `CLAUDE.md`, `CONTEXT.md`, `HANDOVER.md` into it.
3. `cd` into that directory and run `claude` (Claude Code).
4. Paste the contents of `KICKOFF_PROMPT.md` as your first message.
5. Claude will read everything, enter Opus plan mode, and produce a Stage 1 plan.
6. Review the plan → approve → let it execute → confirm Stage 1 checkpoints → say "proceed to Stage 2".
7. Repeat through Stage 5.

## Session continuity

When you start a new session (new chat, next day, etc.):
- Just say "continue" or paste this short prompt:

  > Read CONTEXT.md and the last 5 entries of HANDOVER.md. Tell me current stage, last verified state, and the next concrete task. Then enter plan mode if there's non-trivial work ahead.

- Claude will pick up exactly where it left off.

## Hard rules baked into the setup

- Opus plan mode before non-trivial work
- Parallel subagents for independent work (scaffolding, research, isolated tests)
- Stage gates require explicit user approval to cross
- V1 only — no V2 work
- Never edit SPEC.md
- Ask before deciding anything not in the spec
