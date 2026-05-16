# ARIA v1 — System Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL WORLD                                     │
│                                                                                 │
│   IoT Sensors ──┐    Citizen Reports ──┐    Weather Services ──┐                │
│                 │                      │                       │                │
│                 ▼                      ▼                       ▼                │
│            ┌──────────────────────────────────────────────┐                     │
│            │     POST /api/webhook/alert                  │                     │
│            │     External Event Ingress                   │                     │
│            └──────────────────┬───────────────────────────┘                     │
│                               │                                                 │
└───────────────────────────────┼─────────────────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────────────────┐
│                               ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         FASTAPI SERVER (port 8090)                       │    │
│  │                                                                         │    │
│  │   Endpoints:                                                            │    │
│  │   • GET  /health              — liveness check                          │    │
│  │   • POST /api/incident/create — operator triggers mission               │    │
│  │   • POST /api/webhook/alert   — external event ingress                  │    │
│  │   • GET  /api/pipeline/status — orchestrator introspection              │    │
│  │   • WS   /ws                  — real-time telemetry + agent stream      │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                               │                                                 │
│                               ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                     ORCHESTRATOR (LangGraph + SQLite)                    │    │
│  │                                                                         │    │
│  │   Deterministic state machine — NOT an LLM                              │    │
│  │                                                                         │    │
│  │   States: STANDBY → SURVEILLANCE → SWARM → ADVISORY → RELIEF → END     │    │
│  │                                                                         │    │
│  │   ┌─────────────┐    ┌──────────────┐    ┌───────────────┐             │    │
│  │   │ EventBus    │    │ Incident     │    │ SQLite        │             │    │
│  │   │ (pub/sub)   │    │ Manager      │    │ Checkpointer  │             │    │
│  │   │ 500ms coal. │    │ (priority Q) │    │ (crash-safe)  │             │    │
│  │   └─────────────┘    └──────────────┘    └───────────────┘             │    │
│  └────────────┬────────────────┬─────────────────┬──────────────────────────┘    │
│               │                │                 │                               │
│               ▼                ▼                 ▼                               │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                        AGENT LAYER                                      │     │
│  │                                                                         │     │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  │     │
│  │  │  AGENT 1           │  │  AGENT 2           │  │  AGENT 3           │  │     │
│  │  │  Surveillance      │  │  Specialist Swarm  │  │  Advisory          │  │     │
│  │  │  ─────────────     │  │  ─────────────     │  │  ─────────────     │  │     │
│  │  │  Claude Haiku API  │  │  Claude Haiku API  │  │  Claude Haiku API  │  │     │
│  │  │                    │  │                    │  │                    │  │     │
│  │  │  Tools:            │  │  Tools:            │  │  Tools:            │  │     │
│  │  │  • fly_to          │  │  • fly_to          │  │  • issue_advisory  │  │     │
│  │  │  • get_sensor      │  │  • find_base       │  │                    │  │     │
│  │  │  • get_live_weather│  │  • launch_from_base│  │  Triggers:         │  │     │
│  │  │  • report_class.   │  │  • get_sensor      │  │  • A1 report       │  │     │
│  │  │                    │  │  • report_findings  │  │  • A2 findings     │  │     │
│  │  │  Drones: 1-2       │  │                    │  │  • world_event     │  │     │
│  │  │  fixed-wing        │  │  Drones: 2-4       │  │  • heartbeat       │  │     │
│  │  │  120m AGL          │  │  rotary/mixed      │  │  • operator_query  │  │     │
│  │  │                    │  │  15-100m AGL       │  │                    │  │     │
│  │  └───────────────────┘  └───────────────────┘  └───────────────────┘  │     │
│  │                                                                         │     │
│  │  ┌───────────────────┐                                                  │     │
│  │  │  AGENT 4           │  ┌─────────────────────────────────────────┐    │     │
│  │  │  Relief Coord.     │  │  RESILIENCE LAYER (agents/resilience.py)│    │     │
│  │  │  ─────────────     │  │  • Exponential backoff (3 retries)      │    │     │
│  │  │  Claude Haiku API  │  │  • Cached fallback responses            │    │     │
│  │  │                    │  │  • Graceful degradation on API failure   │    │     │
│  │  │  Tools:            │  └─────────────────────────────────────────┘    │     │
│  │  │  • find_nearest_rc │                                                  │     │
│  │  │  • dispatch_unit   │                                                  │     │
│  │  │  • issue_plan      │                                                  │     │
│  │  └───────────────────┘                                                  │     │
│  └─────────────────────────────────────────────────────────────────────────┘     │
│               │                                                                  │
│               ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐     │
│  │                      SIMULATION LAYER                                    │     │
│  │                                                                          │     │
│  │  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────────┐   │     │
│  │  │ DroneModel      │  │ WorldState      │  │ SensorOverlay           │   │     │
│  │  │ (kinematic)     │  │ (markers, zones │  │ (synthetic returns per  │   │     │
│  │  │                 │  │  survivors,     │  │  zone/drone position)   │   │     │
│  │  │ DroneInterface  │  │  hazards)       │  │                         │   │     │
│  │  │ ↑ abstract      │  │                 │  │  Information contract:  │   │     │
│  │  │ (V2: SITL swap) │  │ Tick: 10 Hz    │  │  SHARED_TO_AGENTS       │   │     │
│  │  │                 │  │                 │  │  HIDDEN_FROM_AGENTS     │   │     │
│  │  └────────────────┘  └────────────────┘  └─────────────────────────┘   │     │
│  │                                                                          │     │
│  │  ┌────────────────┐  ┌────────────────────────────────────────────┐     │     │
│  │  │ Scenarios       │  │ World Events                               │     │     │
│  │  │ • fire.json     │  │ • fire_growth (radius expansion)           │     │     │
│  │  │ • structural_   │  │ • external_alert (webhook-triggered)       │     │     │
│  │  │   collapse.json │  │ • aftershock (future events)               │     │     │
│  │  │ • flood.json    │  │                                            │     │     │
│  │  │ • industrial_   │  │ Agents CANNOT see:                         │     │     │
│  │  │   hazard.json   │  │ • world_seed, future_events, other_agent   │     │     │
│  │  │ • maritime_sar  │  │   reasoning, full_zone_graph               │     │     │
│  │  └────────────────┘  └────────────────────────────────────────────┘     │     │
│  └──────────────────────────────────────────────────────────────────────────┘     │
│               │                                                                  │
│               ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐     │
│  │                     OBSERVABILITY (sim_layer/tracer.py)                   │     │
│  │                                                                          │     │
│  │  Structured trace spans → traces/ directory (JSON)                       │     │
│  │  • Agent invocation spans (start/end, duration)                          │     │
│  │  • Tool call spans (input/output, parent linkage)                        │     │
│  │  • Webhook event spans                                                   │     │
│  │  • Orchestrator state transition spans                                   │     │
│  │  • Causal parent→child linking via span_id/parent_id                     │     │
│  │                                                                          │     │
│  │  Ready for Omium SDK swap (same span interface)                          │     │
│  └──────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           OPERATOR FRONTEND                                       │
│                                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │                    Mapbox GL JS (Dark Tactical Theme)                     │    │
│  │                                                                          │    │
│  │  • Drone markers (RAF lerp 500ms + CSS heading rotation)                 │    │
│  │  • Incident markers (color-coded by type)                                │    │
│  │  • Risk zone rings (GeoJSON fill + line layers)                          │    │
│  │  • Survivor pins                                                         │    │
│  │  • Deployment bases (5 pre-positioned sites)                             │    │
│  │  • Response centre overlay (17 centres, color by type)                   │    │
│  │  • Swarm satellite visualization (4x drones around leader)               │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │                 SidePanel (Glass UI — Liquid Glass Design)                │    │
│  │                                                                          │    │
│  │  • Zone draw → Type selection → Severity → Deploy                        │    │
│  │  • Agent status dots (idle/active/done/error + pulse animation)          │    │
│  │  • Live pipeline feed (color-coded by agent, 200 entry buffer)           │    │
│  │  • Advisory panel (structured output: actions, zones, resources)          │    │
│  │  • Relief plan panel (dispatched units, ETAs, routes)                     │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                   │
│  Tech: React 18 + Vite + framer-motion + WebSocket (single batched connection)   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow — End-to-End Mission

```
                    TRIGGER
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    Operator UI   Webhook Alert   World Event
    (map click)   (IoT/citizen)   (fire_growth)
         │             │             │
         └─────────────┼─────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  GO SIGNAL      │
              │  (coordinates + │
              │   type_hint)    │
              └────────┬────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │       LANGGRAPH STATE MACHINE        │
    │                                      │
    │  ┌────────────────────────────────┐  │
    │  │ NODE 1: Surveillance           │  │
    │  │                                │  │
    │  │  1. Fetch live weather (API)   │  │
    │  │  2. Fly to incident zone       │  │
    │  │  3. Expanding orbit (180m,     │  │
    │  │     300m × 8 points each)      │  │
    │  │  4. Sensor readings            │  │
    │  │  5. LLM classification         │  │
    │  │     (with retry × 3)           │  │
    │  │  6. Report to orchestrator     │  │
    │  └───────────────┬────────────────┘  │
    │                  │                    │
    │                  ▼                    │
    │  ┌────────────────────────────────┐  │
    │  │ NODE 2: Specialist Swarm       │  │
    │  │                                │  │
    │  │  SWARM_CAPABILITIES table:     │  │
    │  │  fire → thermal_rotary (3)     │  │
    │  │  collapse → micro_search (4)   │  │
    │  │  flood → fixed_wing_ext (2)    │  │
    │  │  industrial → standoff (2)     │  │
    │  │  maritime → endurance (3)      │  │
    │  │                                │  │
    │  │  1. Select nearest base        │  │
    │  │  2. Launch swarm drones        │  │
    │  │  3. Execute priority tasks     │  │
    │  │  4. Report findings            │  │
    │  └───────────────┬────────────────┘  │
    │                  │                    │
    │                  ▼                    │
    │  ┌────────────────────────────────┐  │
    │  │ NODE 3: Advisory               │  │
    │  │                                │  │
    │  │  Input: A1 + A2 combined       │  │
    │  │  Output: Structured plan       │  │
    │  │  • Situation summary           │  │
    │  │  • Immediate actions           │  │
    │  │  • Exclusion zones             │  │
    │  │  • Resource requirements       │  │
    │  │  • Risk flags                  │  │
    │  │  • Monitoring status           │  │
    │  │                                │  │
    │  │  Re-triggers on: world_event,  │  │
    │  │  new A2 data, heartbeat        │  │
    │  └───────────────┬────────────────┘  │
    │                  │                    │
    │                  ▼                    │
    │  ┌────────────────────────────────┐  │
    │  │ NODE 4: Relief Coordination    │  │
    │  │                                │  │
    │  │  1. Match 17 response centres  │  │
    │  │  2. Calculate ETAs             │  │
    │  │  3. Dispatch units by type     │  │
    │  │  4. Issue ground response plan │  │
    │  └───────────────┬────────────────┘  │
    │                  │                    │
    │                  ▼                    │
    │              END (trace saved)        │
    └──────────────────────────────────────┘
                       │
                       ▼
              Operator sees:
              • Drones moving on map
              • Live agent reasoning stream
              • Structured advisory
              • Ground unit dispatch plan
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18 + Vite + Mapbox GL JS | Tactical operator interface |
| Transport | WebSocket (batched frames) | Real-time telemetry at 10 Hz |
| Server | FastAPI + Uvicorn | REST + WS, async event loop |
| Orchestration | LangGraph + SQLite Checkpointer | Crash-safe state machine |
| Agent Reasoning | Claude Haiku API (tool_choice enforced) | Classification, planning, advisory |
| Web Search | Open-Meteo API (httpx) | Live weather at incident coords |
| Event Ingress | Webhook endpoint + EventBus | External alerts → pipeline |
| Resilience | Exponential backoff + cached fallback | Graceful API failure handling |
| Simulation | Kinematic DroneModel (DroneInterface) | V2-ready SITL seam |
| Observability | Structured tracer (JSON spans) | Full pipeline traceability |
| Logging | structlog (ISO timestamps) | Structured operational logging |

---

## File Structure

```
aria/
├── main.py                          # FastAPI server, WS, webhook, pipeline status
├── config.yaml                      # Ports, models, scenario
│
├── agents/
│   ├── base_agent.py                # Observe/reason/act template
│   ├── agent1_surveillance.py       # Survey + classification + weather
│   ├── agent2_specialist.py         # Swarm deployment + findings
│   ├── agent3_advisory.py           # Structured advisory generation
│   ├── agent4_relief.py             # Ground response coordination
│   ├── resilience.py                # Retry with exponential backoff
│   ├── messages.py                  # Pydantic inter-agent contracts
│   └── tools/
│       ├── flight_tools.py          # fly_to, find_base, launch_from_base
│       ├── sensor_tools.py          # get_sensor_reading
│       ├── report_tools.py          # report_classification, issue_advisory
│       ├── relief_tools.py          # find_nearest_rc, dispatch_unit
│       └── web_search_tools.py      # get_live_weather (Open-Meteo)
│
├── orchestrator/
│   ├── orchestrator.py              # LangGraph state machine + tracer
│   ├── incident_manager.py          # Multi-incident priority queue
│   ├── event_bus.py                 # Pub/sub with 500ms coalesce
│   └── classifier.py                # NL → scenario mapping
│
├── sim/
│   ├── drone_interface.py           # Abstract base (V2 SITL seam)
│   ├── drone_model.py               # Kinematic model
│   ├── world_state.py               # Zones, markers, bases, telemetry
│   ├── sensor_overlay.py            # Synthetic sensor returns
│   └── scenarios/                   # 5 disaster scenario JSONs
│
├── sim_layer/
│   └── tracer.py                    # Structured observability spans
│
├── prompts/
│   ├── registry.py                  # Versioned prompt loading
│   └── *.md                         # Agent system prompts
│
├── frontend/src/
│   ├── App.jsx                      # Root + WebSocket handler
│   ├── Map.jsx                      # Mapbox GL tactical map
│   ├── SidePanel.jsx                # Glass UI command panel
│   ├── MapStateManager.js           # Batched GeoJSON writer
│   ├── DroneManager.js              # RAF drone animation
│   └── DispatchAnimation.js         # Swarm deploy visual
│
└── traces/                          # JSON trace output
```
