# ARIA — Autonomous Response & Incident Agent

**Multi-agent autonomous drone swarm system for disaster response.**

ARIA detects disasters from real-world event feeds, autonomously dispatches simulated drone reconnaissance, classifies the incident through agent reasoning over live sensor and web data, deploys a specialist swarm, and issues an actionable response plan to first responders — end to end, without a human in the loop.

> Built for Problem 03/04 — *Multi-agent autonomy that ships real work, end-to-end.*

---

## Table of Contents

1. [What ARIA Does](#what-aria-does)
2. [Why It Matters](#why-it-matters)
3. [System Architecture](#system-architecture)
4. [The Agent Pipeline](#the-agent-pipeline)
5. [Real-World Capabilities](#real-world-capabilities)
6. [Tech Stack](#tech-stack)
7. [Project Structure](#project-structure)
8. [Quickstart](#quickstart)
9. [Configuration](#configuration)
10. [Running a Scenario](#running-a-scenario)
11. [The Operator Interface](#the-operator-interface)
12. [How Autonomy Works](#how-autonomy-works-in-practice)
13. [Observability & Tracing](#observability--tracing)
14. [Testing](#testing)
15. [Demo Script](#demo-script)
16. [Judging Alignment](#judging-alignment)
17. [Known Limitations](#known-limitations)
18. [Dependencies](#dependencies)

---

## What ARIA Does

A disaster happens. ARIA finds out — either from a real-world event feed (a USGS earthquake webhook, a weather alert) or from an operator dropping a marker on the map. From that trigger forward, no human steers the system:

1. **Agent 1 (Surveillance)** autonomously launches a fixed-wing drone, flies it to the incident region, and classifies what it actually finds from sensor data and live web research — it may confirm or overturn the initial hint.
2. **The Orchestrator** routes Agent 1's verified classification through a deterministic state machine and selects the correct specialist response.
3. **Agent 2 (Specialist Swarm)** picks the nearest capable drone base, launches a swarm, runs the disaster-specific mission (perimeter mapping, survivor detection, hazard standoff), and reports structured findings.
4. **Agent 3 (Advisory)** synthesizes everything — surveillance, swarm findings, live web context — into a first-responder response plan and pushes it out as a real side-effect (a posted message / filed report).
5. Drones return to base. The advisory updates as conditions evolve.

The entire loop runs autonomously and is fully observable in a live agent log.

---

## Why It Matters

Disaster response is bottlenecked on **situational awareness in the first 30 minutes**. Responders arrive without knowing where survivors are, which structures are unsafe, where the hazard is spreading, or what the evacuation picture looks like. ARIA's premise: autonomous aerial agents can build that picture and hand responders a written plan before boots are on the ground.

Target users: emergency operations centers, search-and-rescue coordinators, wildfire incident command. The system is designed so the simulated drone layer (V1) swaps for a real flight stack (ArduPilot SITL, then real airframes) in V2 **without touching agent code** — the `DroneInterface` abstraction is the seam.

---

## System Architecture

```
   REAL-WORLD TRIGGERS                      OPERATOR TRIGGER
   USGS quake feed / weather alert          marker drop on map
        │  (webhook ingress)                     │
        └──────────────┬─────────────────────────┘
                        ▼
            ┌───────────────────────────┐
            │       ORCHESTRATOR        │
            │  LangGraph state machine  │
            │  + SQLite checkpointer    │   deterministic, crash-safe
            │  STANDBY → SURVEILLANCE   │
            │  → SWARM → ADVISORY       │
            │  → MULTI_INCIDENT / EMERG │
            └────────────┬──────────────┘
                          ▼
            ┌───────────────────────────┐
            │     INCIDENT MANAGER      │   one isolated stack per incident
            └────────────┬──────────────┘
                          ▼
   ┌───────────────────────────────────────────────────┐
   │                INCIDENT STACK                     │
   │                                                   │
   │  AGENT 1 — Surveillance      (Claude API)        │
   │   • single fixed-wing drone                       │
   │   • flies to region, reads sensors                │
   │   • web search for live context                   │
   │   • classifies → SurveillanceReport               │
   │            │ typed handoff                        │
   │            ▼                                       │
   │  AGENT 2 — Specialist Swarm  (Claude API)        │
   │   • picks nearest matching base                   │
   │   • launches 5-drone swarm                         │
   │   • runs disaster-specific mission                 │
   │   • → IncidentBriefing                             │
   └────────────┬──────────────────────────────────────┘
                 ▼
   ┌───────────────────────────────────────────────────┐
   │  AGENT 3 — Advisory   (Claude API, shared)        │
   │   • event-driven (triggers, not a loop)           │
   │   • web search for shelters / routes / conditions │
   │   • emits structured response plan                 │
   │   • real outbound side-effect (post / file)        │
   └────────────┬──────────────────────────────────────┘
                 ▼
        OPERATOR SCREEN  (map · agent log · advisory)

   SIMULATION LAYER (parallel, isolated by a data contract)
   DroneModel (kinematic, DroneInterface) → World State
   (FastAPI + WebSocket) → controlled data share → agents
```

### Key design principles

- **The Orchestrator is not an LLM.** It is a deterministic LangGraph state machine. Speed, reliability, crash-safety. Decisions are made by agents; routing is made by the graph.
- **Agents are isolated.** Each agent runs with its own message context. Agent 2 receives Agent 1's *conclusions*, never its reasoning. Enforced and tested with a poison-string isolation test.
- **The sim/agent boundary is a contract**, not a wall and not god-mode. Agents see markers, telemetry, and sensor data. Agents never see the world seed, future events, or the full zone graph — they discover by flying.
- **Nothing load-bearing is scripted.** Classification, base selection, swarm tasking, advisory generation, and return-to-base are all real Claude API tool calls, visible in the trace.

---

## The Agent Pipeline

### Agent 1 — Surveillance (Claude API)

Controls one fixed-wing reconnaissance drone. Receives a go-signal with approximate coordinates and a disaster *hint*. Flies to the region, completes a full orbit, pulls sensor readings, and runs a web search for corroborating live reports. Then it classifies — and it is explicitly allowed to **overturn the operator's hint** if its sensors and research disagree. Outputs a typed `SurveillanceReport` (classification, confidence, affected area, hint-confirmed flag).

Tools: `fly_to`, `loiter_over`, `get_sensor_reading`, `web_search`, `report_classification`, `request_detailed_pass`.

### Agent 2 — Specialist Swarm (Claude API)

Receives the verified `SurveillanceReport`. Looks up the locked swarm decision table (`SWARM_CAPABILITIES`) for the confirmed disaster type — the agent **reasons within** the chosen config but does not pick the swarm type (that is deterministic, by design). Finds the nearest drone base whose stock matches, launches a 5-drone swarm, runs the disaster-specific priority tasks under the operational constraint (e.g., maintain upwind position for fire, 200 m standoff for industrial hazard), and emits an `IncidentBriefing`.

Tools: `find_nearest_base`, `launch_from_base`, batch swarm command, `get_sensor_reading`, `update_zone_classification`, `mark_survivor`, `mark_hazard`, `report_swarm_findings`.

### Agent 3 — Advisory (Claude API, event-driven, shared across incidents)

Not a loop. Fires on triggers: a new surveillance report, updated swarm findings, a world event (fire grows), an operator query, or a 60 s heartbeat. Synthesizes all incident data plus live web research (shelter locations, evacuation routes, current weather) into a fixed-format response plan: situation summary, immediate actions, exclusion zones, resource requirements, risk flags, monitoring. Pushes the advisory out as a real side-effect.

Output is schema-enforced via tool use.

---

## Real-World Capabilities

ARIA is built to satisfy the full required-capability set of the brief, not just the multi-agent core:

| Capability | How ARIA does it |
|---|---|
| **Multi-agent** | 3 specialized agents + deterministic orchestrator, typed handoffs, agent isolation |
| **Autonomy** | Real-world event feed triggers the pipeline with zero human input; agents make every classification and tasking decision |
| **Long-running** | Webhook-triggered incidents run beyond the interactive window; heartbeat + world events keep advisories live; SQLite checkpointer makes it crash-safe |
| **Deep reasoning** | Agents decompose, plan, reflect across multi-turn tool loops; Agent 1 can overturn the operator hint |
| **Tool calling** | Flight control, sensors, base logistics, classification, annotation — all real tool calls with side-effects on world state |
| **Web search** | Agent 1 corroborates classification with live reports; Agent 3 pulls live shelters/routes/weather into the plan |
| **Webhooks** | External event ingress from a real disaster feed (USGS / weather alerts) wakes ARIA autonomously |
| **Async orchestration** | Incidents fan out via the IncidentManager; agents complete on their own timeline and return to the planner |

> **Build status note:** The simulation, agent pipeline, orchestrator, prompt registry, and typed-comms layer are the core build. The real-world ingress (webhook feed), `web_search` tool, and outbound side-effect are the **final integration layer** — they are the intended production architecture and the demo's autonomy story. Where a section below describes these, it describes the target system.

---

## Tech Stack

| Component | Technology |
|---|---|
| Flight simulation | `DroneModel` kinematic, `DroneInterface` abstraction (SITL-ready for V2) |
| World state | FastAPI + in-memory |
| Inter-process comms | FastAPI WebSocket |
| Agents 1 & 2 reasoning | Claude API (`claude-sonnet-4-20250514`) |
| Agent 3 reasoning | Claude API, tool-use schema enforcement |
| Orchestrator | LangGraph + SQLite checkpointer |
| Inter-agent messages | Pydantic typed models (`SurveillanceReport`, `IncidentBriefing`, `WorldEvent`) |
| Prompt system | File-based registry with version hashing |
| Event bus | In-process pub/sub with coalescing (Agent 3 triggers) |
| Frontend map | Mapbox GL JS, dark style |
| Map state | `MapStateManager` — single writer, batched GeoJSON on 1 s interval |
| Drone animation | requestAnimationFrame lerp (500 ms) + CSS heading rotation |
| Real-world ingress | Webhook receiver (USGS / weather feed) |
| Web search | Live search tool exposed to Agents 1 & 3 |
| Outbound side-effect | Advisory pushed via webhook (Slack / email / issue) |
| Tracing | Omium SDK (optional bonus) → mock tracer fallback |

---

## Project Structure

```
aria/
├── sim/
│   ├── drone_interface.py      # abstract — SITL swaps in here in V2
│   ├── drone_model.py          # kinematic model, implements DroneInterface
│   ├── world_state.py          # zone graph, markers, bases, tick loop
│   ├── sensor_overlay.py       # synthetic sensor returns per position
│   └── scenarios/              # fire / collapse / flood / industrial / maritime
│
├── agents/
│   ├── base_agent.py           # observe / reason / act loop
│   ├── agent1_surveillance.py  # loads prompt from registry
│   ├── agent2_specialist.py    # swarm + base logistics
│   ├── agent3_advisory.py      # event-driven, schema-enforced
│   ├── messages.py             # typed handoff models
│   └── tools/
│       ├── flight_tools.py     # fly_to, loiter_over, rtl, abort
│       ├── sensor_tools.py     # get_sensor_reading
│       ├── base_tools.py       # find_nearest_base, launch_from_base
│       ├── search_tools.py     # web_search
│       ├── report_tools.py     # report_classification, issue_advisory
│       └── schemas.py          # Pydantic tool schemas + to_claude_tool_dict()
│
├── prompts/
│   ├── registry.py             # load_prompt(name) -> (text, version_hash)
│   ├── agent1_surveillance.md
│   ├── agent2_specialist.md
│   ├── agent3_advisory.md
│   └── _shared/                # output_contracts.md, safety_rules.md, notes.md
│
├── orchestrator/
│   ├── orchestrator.py         # LangGraph state machine + SQLite checkpointer
│   ├── incident_manager.py     # multi-incident handler
│   ├── event_bus.py            # pub/sub, coalescing (Agent 3 triggers)
│   ├── classifier.py           # natural language / feed → scenario
│   └── webhook_receiver.py     # real-world event ingress
│
├── sim_layer/
│   ├── map_state_manager.py    # single Mapbox writer, batched GeoJSON
│   └── tracer.py               # Omium mock → real SDK swap
│
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── Map.jsx             # drones, swarm cluster, markers, bases, rings
│       ├── SetupPanel.jsx      # collapsible scenario setup (area + hint)
│       ├── AgentStream.jsx     # live agent log
│       ├── AdvisoryPanel.jsx   # Agent 3 output
│       └── DroneStatus.jsx     # fleet status + telemetry
│
├── main.py                     # starts everything
├── config.yaml                 # ports, model names, feeds, scenario paths
├── SPEC.md                     # build specification (read-only)
├── CONTEXT.md                  # cross-session context
├── HANDOVER.md                 # running build log
└── README.md                   # this file
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node 18+
- An Anthropic API key
- A Mapbox access token (free tier is fine)
- (Optional) Omium SDK credentials for the tracing bonus

### Setup

```bash
# 1. Clone
git clone <repo-url> aria && cd aria

# 2. Python environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend
cd frontend && npm install && cd ..

# 4. Environment variables
cp .env.example .env
# edit .env — see Configuration below
```

### Run

```bash
python main.py
```

This starts the FastAPI backend, the WebSocket server, the orchestrator, and the frontend dev server. Open the printed local URL (default `http://localhost:5173`) for the operator screen.

A clean run from these steps produces a green demo. If it does not, that is a bug — see [Testing](#testing).

---

## Configuration

`.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
MAPBOX_TOKEN=pk....
# Optional — real-world ingress
USGS_FEED_REGION=...                # bounding box or region filter
WEBHOOK_PUBLIC_URL=...              # where the feed posts events
# Optional — outbound side-effect
OUTBOUND_WEBHOOK_URL=...            # Slack / Discord / etc.
# Optional — tracing bonus
OMIUM_API_KEY=...
```

`config.yaml` holds non-secret config: ports, model strings, scenario file paths, base placement, event-bus coalescing window, heartbeat interval. Do not put secrets here.

---

## Running a Scenario

### Operator-triggered (interactive demo)

1. Open the operator screen.
2. Expand the setup side panel.
3. Select an area on the map and a disaster *hint* (e.g., "possible fire").
4. Drop the marker. The setup panel auto-collapses.
5. Watch: Agent 1 launches, flies, classifies (it may overturn your hint), Agent 2 deploys the swarm from the nearest matching base, Agent 3 issues the advisory and pushes it out. Drones return to base.

### Autonomously triggered (the real autonomy story)

1. Start ARIA with the webhook receiver enabled and a feed configured.
2. When a qualifying real-world event arrives (or a simulated webhook is fired into the receiver), ARIA wakes on its own.
3. The full pipeline runs with **no operator input**. The agent log narrates every decision.

---

## The Operator Interface

- **Map** — drones, swarm cluster (Agent 2 renders as one leader icon + 4 satellites moving as a unit), incident markers, drone bases, risk rings. All aircraft use a single uniform icon; movement is smooth waypoint interpolation, never teleporting or jitter.
- **Setup panel** — collapsible, hidden by default during the demo. Area + disaster-hint selectors live here.
- **Agent log** — live structured stream of every agent action and tool call (timestamp · agent · event · summary). This is how a judge *sees* the autonomy.
- **Advisory panel** — Agent 3's response plan, formatted into its six fixed sections, updating as conditions evolve.

---

## How Autonomy Works in Practice

Autonomy here is not "the prompt does a lot." It is structural:

- **Triggering is external.** A real webhook, not a human, starts an incident in the autonomous path.
- **Classification is earned, not given.** Agent 1 is handed a hint and is explicitly empowered to reject it based on sensor and web evidence. The downstream swarm is chosen from Agent 1's verdict, so a wrong hint does not corrupt the response.
- **Tasking is delegated.** Agent 2 chooses the base and plans the swarm mission within hard constraints; the orchestrator never makes that decision.
- **Reaction is event-driven.** Agent 3 re-issues advisories when the world changes, on its own, via the event bus.
- **Recovery is automatic.** Kill the orchestrator mid-incident; the SQLite checkpointer restores the last clean state within ~10 s and the pipeline continues.

Every one of these is a real Claude API tool call and appears in the agent log and (if enabled) the Omium trace. There is no hidden script sequencing the demo.

---

## Observability & Tracing

- **Agent log** (always on) — every agent step and tool call streamed to the UI and stdout.
- **Omium SDK tracing** (optional, bonus axis) — when `OMIUM_API_KEY` is set, every agent invocation, tool call, webhook fire, and async dispatch is instrumented and causally linked: a webhook-triggered subworkflow links back to its origin; sub-agents link to their parent step. The dashboard becomes a verifiable record that matches the demo exactly.
- **Mock tracer fallback** — if Omium auth fails, a structurally identical mock tracer prints the trace to the terminal so the demo never breaks on an observability dependency.

---

## Testing

```bash
pytest                       # unit + integration suite
```

The system ships with a staged acceptance protocol (see `SPEC.md` build order) and a `FULL_SYSTEM_TEST.md` end-to-end protocol covering nine surfaces: process lifecycle, data contracts, drone kinematics, agent reasoning loops, orchestration, map rendering, end-to-end happy path, multi-incident, and failure-mode fallbacks. Each integration also produces a report artifact (`AUDIT_REPORT.md`, `INTEGRATION_REPORT.md`) as a verifiable record of what passed.

The agent-isolation guarantee is pinned by a dedicated test: a sentinel string injected into Agent 1's context must never appear in Agent 2 or Agent 3.

---

## Demo Script

A reliable 5-minute walkthrough:

1. **0:00 — Setup (15s).** Operator screen, side panel collapsed. One line on the problem: responders are blind in the first 30 minutes.
2. **0:15 — Autonomous trigger (45s).** Fire a webhook (or show the live feed catch a real event). ARIA wakes with no input. Agent log starts narrating.
3. **1:00 — Surveillance (75s).** Agent 1 launches, flies to the region, orbits, reads sensors, runs a web search, and classifies — show it overturning a wrong hint.
4. **2:15 — Swarm (75s).** Agent 2 picks the nearest matching base, launches the 5-drone swarm, runs the mission. Swarm cluster moves on the map.
5. **3:30 — Advisory (60s).** Agent 3 synthesizes everything plus live web context into the response plan; it is pushed out as a real side-effect (show the posted message).
6. **4:30 — Recovery + close (30s).** Kill the orchestrator; show it restore and continue. Open the Omium dashboard — same workflow, same steps.

Have a fallback recording of this exact run. A polished crash-recovery story beats an ambitious crash.

---

## Judging Alignment

| Axis | Weight | Where ARIA scores it |
|---|---|---|
| 01 Problem relevance & usefulness | 20% | Real bottleneck (first-30-minutes situational awareness), clear users, V2 path to real airframes |
| 02 Autonomous execution | 25% | External webhook trigger, agent-earned classification, delegated tasking, automatic recovery |
| 03 Multi-agent workflow quality | 20% | 3 isolated specialized agents, typed handoffs, deterministic orchestration |
| 04 Tooling & integrations | 15% | Flight/sensor/base tools with side-effects, live web search, webhook ingress, outbound side-effect |
| 05 Demo video quality | 10% | Tight end-to-end script, autonomy visible in the agent log, crash-recovery shown |
| 06 Technical architecture | 10% | LangGraph + Pydantic + prompt registry + event bus; clean modular structure; full observability |
| Bonus Omium verified tracing | +10% | Complete causal coverage, dashboard matches demo |

---

## Known Limitations

- **V1 uses a kinematic drone model**, not full flight dynamics. Intentional. `DroneInterface` is the seam; ArduPilot SITL is a V2 drop-in that touches zero agent code.
- **Swarm is visually 1 leader + 4 satellites.** Mission logic uses the spec's per-disaster drone counts; the visual count is decoupled for render performance and clarity.
- **Scenario coverage in V1** focuses on the demo-critical disaster types; full 5-scenario depth and fully parallel multi-incident stacks are V2.
- **Predictive modeling** (collapse propagation, fire-spread forecasting) is V2.
- **Human override controls** are V2 — V1 is deliberately hands-off to demonstrate autonomy.

---

## Dependencies

| Dependency | Purpose | Required |
|---|---|---|
| Anthropic API | Agents 1, 2, 3 reasoning | Yes |
| Mapbox GL JS | Operator map | Yes |
| LangGraph | Orchestrator state machine + checkpointer | Yes |
| FastAPI / Uvicorn | World state + WebSocket | Yes |
| Pydantic | Typed inter-agent comms + tool schemas | Yes |
| React + Vite | Operator frontend | Yes |
| USGS / weather feed | Real-world event ingress | Optional (autonomy path) |
| Web search provider | Live context for Agents 1 & 3 | Optional (recommended) |
| Outbound webhook target | Real side-effect for the advisory | Optional (recommended) |
| Omium SDK | Verifiable tracing | Optional (bonus axis) |

All third-party usage and cost is borne by the team. Disclose any added dependency here when introduced.

---

*ARIA — situational awareness before boots on the ground.*
