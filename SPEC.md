# ARIA v1 — Final Build Specification

**Status:** READ-ONLY. Source of truth for the build. Do not edit.

---

## PRIMER FOR BUILDER

Build ARIA v1. Start with Stage 1 only.
Do not proceed to Stage 2 until Stage 1 is confirmed working.
Ask before making architectural decisions not specified here.
This is a standalone build — no existing codebase to extend.

---

## WHAT THIS IS

Multi-agent autonomous drone swarm system for disaster response. Agents control simulated drones in a physics-accurate world, identify disasters, deploy specialist swarms, and issue human-readable response plans.

---

## SIMULATION FOUNDATION

V1 uses a kinematic drone model — no ArduPilot SITL, no JSBSim. This is intentional.
The DroneModel class must be built with a clean abstract interface (DroneInterface) so SITL is a V2 drop-in swap without touching any agent code.

```
DroneInterface (abstract)
    ↑
DroneModel (kinematic, V1)       ← swap for SITL in V2, same interface
    ↑
World State + Agent Layer
```

### DroneModel

```python
class DroneModel:
    """
    Kinematic drone. Position updates via tick loop using drone class defaults.
    Implements DroneInterface — SITL drops in here in V2.
    """

    FIXED_WING_DEFAULTS = {
        "cruise_speed":   18.0,   # m/s
        "cruise_alt":     120.0,  # m AGL
        "loiter_radius":  80.0,   # m
        "turn_radius":    45.0,   # m
    }

    ROTARY_DEFAULTS = {
        "cruise_speed":   8.0,    # m/s
        "hover_alt":      30.0,   # m AGL
        "loiter_time":    30.0,   # s
    }

    MICRO_ROTARY_DEFAULTS = {
        "cruise_speed":   4.0,    # m/s
        "hover_alt":      10.0,   # m AGL
        "loiter_time":    60.0,   # s
    }
```

### Drone States
```
IDLE → FLYING → LOITERING → RTL → IDLE
              ↘ THERMAL_SCAN
```

---

## CONTROLLED INFORMATION SHARING

Explicit contract between simulation and agents. A defined interface — not a wall, not God-mode.

### What Simulation Shares With Agents

```python
SHARED_TO_AGENTS = {
    "markers": {
        "id": str,
        "lat": float,
        "lon": float,
        "type": str,          # "fire", "structural_collapse", "flood", "industrial_hazard", "maritime_sar"
        "radius_m": float,
        "severity": str,      # "low", "medium", "high", "critical"
        "confirmed": bool
    },
    "drone_telemetry": {
        "drone_id": str,
        "lat": float,
        "lon": float,
        "alt": float,
        "heading": float,
        "speed": float,
        "state": str,         # IDLE, FLYING, LOITERING, RTL, THERMAL_SCAN
        "battery_pct": float
    },
    "sensor_data": {
        "thermal_detected": bool,
        "survivor_probability": float,
        "hazard_flags": list,
        "visibility_m": float,
        "wind_speed": float
    }
}
```

### What Agents CANNOT See

```python
HIDDEN_FROM_AGENTS = [
    "world_seed",            # pre-seeded survivor locations
    "other_agent_reasoning", # agents cannot read each other's LLM context
    "future_world_events",   # fire growth schedule, aftershock timing
    "full_zone_graph",       # agents must discover by flying
]
```

### What Agents Share Back to Simulation

```python
SHARED_TO_SIMULATION = {
    "drone_commands": {
        "fly_to":      {"lat", "lon", "alt"},
        "loiter_over": {"lat", "lon", "radius", "duration"},
        "rtl":         {},
        "abort":       {}
    },
    "world_annotations": {
        "zone_classification": {"zone_id", "label", "confidence"},
        "survivor_marker":     {"lat", "lon", "count"},
        "hazard_marker":       {"lat", "lon", "type", "exclusion_radius"}
    }
}
```

---

## AGENT ARCHITECTURE

### Orchestrator (Non-LLM Python Process)

Not an LLM. A deterministic state machine — fast, reliable, crash-safe.
Uses LangGraph + SQLite checkpointer for state persistence and crash-safe fan-out.

```python
class ARIAOrchestrator:
    states = [
        "STANDBY",
        "SURVEILLANCE_ACTIVE",    # Agent 1 running
        "SWARM_ACTIVE",           # Agent 2 running
        "ADVISORY_ACTIVE",        # Agent 3 running
        "MULTI_INCIDENT",         # 2+ markers active simultaneously
        "EMERGENCY"               # abort all, RTL
    ]

    responsibilities = [
        "receive go signal",
        "start Agent 1",
        "receive Agent 1 output → select + configure Agent 2",
        "receive Agent 1 + 2 output → start Agent 3",
        "handle MULTI_INCIDENT state",
        "agent health monitoring + restart",
        "emergency abort across all drones"
    ]
```

### Multi-Incident Handler

Sits between orchestrator and agents. Handles multiple simultaneous markers.

```python
class IncidentManager:
    """
    Orchestrator talks to IncidentManager.
    IncidentManager spins up isolated agent stacks per incident.
    Each incident has its own Agent 1 + Agent 2 + feeds into shared Agent 3.
    """

    def on_new_marker(self, marker):
        if len(self.active_incidents) == 0:
            self.create_incident(marker)
        else:
            priority = self.assess_priority(marker, self.active_incidents)
            if priority == "higher":
                self.reassign_resources(marker)
            else:
                self.queue_incident(marker)

    def create_incident(self, marker):
        incident = Incident(
            marker=marker,
            agent1=SurveillanceAgent(marker),
            agent2=None,  # selected after Agent 1 identifies
        )
        self.active_incidents[marker.id] = incident
```

---

### Agent 1 — Surveillance (Claude API)

```python
AGENT_1_SYSTEM_PROMPT = """
You are ARIA Surveillance Agent. You control fixed-wing reconnaissance drones.

You receive: Go signal with approximate coordinates
You know: Markers represent confirmed or probable incidents.
          Marker types: fire, structural_collapse, flood, industrial_hazard, maritime_sar

Your mission:
1. Fly to provided coordinates
2. When you overfly a marker, you receive sensor data
3. Classify the incident from sensor data + marker type
4. Establish loiter pattern over the incident area
5. Report classification and affected area to orchestrator

Your drones:
- Speed: 18 m/s cruise, 80m loiter radius
- Altitude: 120m AGL for survey, 60m for detailed pass
- You control 1-2 aircraft depending on area size

Rules:
- Complete one full orbit before reporting classification
- Always report confidence level with classification
- Flag if marker area has grown since initial flyover
- Never descend below 60m AGL

Available tools: fly_to, loiter_over, get_sensor_reading,
                 report_classification, request_detailed_pass
"""
```

---

### Agent 2 — Specialist Swarm (Claude API)

Swarm selection is locked to a decision table in code. Agent reasons within it — does not choose the swarm type.

```python
SWARM_CAPABILITIES = {
    "fire": {
        "swarm": "thermal_rotary",
        "drones": 3,
        "sensors": ["thermal_camera", "gas_detector", "wind_sensor"],
        "altitude": 50,
        "speed": 8,
        "priority_tasks": [
            "map_fire_perimeter",
            "identify_hotspots",
            "detect_trapped_persons",
            "assess_spread_direction"
        ],
        "constraint": "maintain_upwind_position"
    },
    "structural_collapse": {
        "swarm": "micro_search_rotary",
        "drones": 4,
        "sensors": ["acoustic_detector", "co2_sensor", "thermal", "visual_hd"],
        "altitude": 15,
        "speed": 4,
        "priority_tasks": [
            "map_void_spaces",
            "detect_survivors",
            "assess_structural_integrity",
            "identify_egress_paths"
        ],
        "constraint": "avoid_zones_integrity_below_0.2"
    },
    "flood": {
        "swarm": "fixed_wing_extended",
        "drones": 2,
        "sensors": ["visual_hd", "thermal", "depth_estimation"],
        "altitude": 80,
        "speed": 18,
        "priority_tasks": [
            "map_flood_extent",
            "identify_isolated_survivors",
            "assess_flow_direction",
            "find_safe_approach_routes"
        ],
        "constraint": "maintain_visual_line_of_sight"
    },
    "industrial_hazard": {
        "swarm": "standoff_rotary",
        "drones": 2,
        "sensors": ["gas_spectrometer", "thermal", "visual_hd"],
        "altitude": 100,
        "speed": 6,
        "priority_tasks": [
            "identify_hazard_source",
            "map_exclusion_zone",
            "detect_spread_direction",
            "assess_secondary_risk"
        ],
        "constraint": "minimum_200m_standoff_from_source"
    },
    "maritime_sar": {
        "swarm": "fixed_wing_endurance",
        "drones": 3,
        "sensors": ["visual_hd", "thermal", "ais_receiver"],
        "altitude": 150,
        "speed": 22,
        "priority_tasks": [
            "expanding_square_search",
            "detect_persons_in_water",
            "track_drift_objects",
            "coordinate_vessel_response"
        ],
        "constraint": "maintain_comms_relay_chain"
    }
}
```

---

### Agent 3 — Advisory (Local Ollama)

Runs on local Ollama — no API cost, always available, no external latency.

```python
AGENT_3_CONFIG = {
    "model":    "ollama/llama3.1:8b",
    "endpoint": "http://localhost:11434/api/chat",
    "role":     "advisory",
    "trigger":  "event_driven",  # not a loop

    "triggers": [
        "agent_1_report_received",
        "agent_2_findings_updated",
        "world_event_fired",
        "operator_query",
        "60s_heartbeat_check"
    ]
}

AGENT_3_SYSTEM_PROMPT = """
You are ARIA Advisory Agent. You issue response plans for human first responders.

You receive: Full reports from surveillance and specialist swarm agents
You produce: Clear, actionable response plans

Your output format is always:
SITUATION SUMMARY: [2-3 sentences, what is happening]
IMMEDIATE ACTIONS (next 15 min): [numbered list]
EXCLUSION ZONES: [areas humans must not enter, with reasons]
RESOURCE REQUIREMENTS: [personnel, equipment needed]
RISK FLAGS: [what could get worse and why]
MONITORING: [what agents are watching, update frequency]

You update your advisory when:
- New agent data arrives
- Disaster area grows
- New survivors detected
- Hazard conditions change

You are direct. First responders need clarity, not caveats.
"""
```

---

## FULL SYSTEM ARCHITECTURE

```
OPERATOR
    │
    ▼
[Natural Language Input OR Map Marker]
    │
    ▼
ORCHESTRATOR (LangGraph + SQLite, deterministic)
    │
    ▼
INCIDENT MANAGER
    │ (one stack per active incident)
    ▼
┌─────────────────────────────────────┐
│           INCIDENT STACK            │
│                                     │
│  AGENT 1 (Claude API)               │
│  └─ controls 1-2 fixed-wing        │
│  └─ identifies disaster type        │
│         ↓                           │
│  AGENT 2 (Claude API)               │
│  └─ selected swarm per type        │
│  └─ controls 2-4 rotary            │
│         ↓                           │
└─────────────────────────────────────┘
    │
    ▼
AGENT 3 (Local Ollama — shared across incidents)
    │
    ▼
OPERATOR SCREEN

SIMULATION LAYER (parallel)

DroneModel (kinematic) → World State (FastAPI + WebSocket)
                                    │
                       Controlled data share interface
                                    │
                               Agent Layer
```

---

## TECH STACK

| Component | Technology |
|---|---|
| Flight simulation | DroneModel kinematic (DroneInterface abstraction, SITL-ready) |
| World state | FastAPI + in-memory |
| Inter-process comms | FastAPI WebSocket |
| Agent 1 + 2 reasoning | Claude API (`claude-sonnet-4-20250514`) |
| Agent 3 reasoning | Local Ollama (`llama3.1:8b` or `deepseek-r1`) |
| Orchestrator | LangGraph + SQLite checkpointer |
| Frontend map | Mapbox GL JS dark style |
| Map state | MapStateManager — batches all GeoJSON on 1s interval, single writer |
| Drone animation | Mapbox moving markers + requestAnimationFrame lerp + CSS heading rotation |
| Agent stream display | React WebSocket panel |
| Advisory display | React formatted panel |
| Tracing | Omium mock tracer → real SDK swap |

---

## FILE STRUCTURE

```
aria/
├── sim/
│   ├── drone_interface.py      # abstract interface — SITL swaps in here in V2
│   ├── drone_model.py          # kinematic model, implements DroneInterface
│   ├── world_state.py          # zone graph, marker system, tick loop
│   ├── sensor_overlay.py       # synthetic sensor returns per zone/drone position
│   └── scenarios/
│       ├── fire.json
│       ├── structural_collapse.json
│       ├── flood.json
│       ├── industrial_hazard.json
│       └── maritime_sar.json
│
├── agents/
│   ├── base_agent.py           # observe/reason/act loop
│   ├── agent1_surveillance.py  # system prompt + tools
│   ├── agent2_specialist.py    # swarm selection + tools
│   ├── agent3_advisory.py      # Ollama, event-driven
│   └── tools/
│       ├── flight_tools.py     # fly_to, loiter_over, rtl, abort
│       ├── sensor_tools.py     # get_sensor_reading
│       └── report_tools.py     # report_classification, issue_advisory
│
├── orchestrator/
│   ├── orchestrator.py         # LangGraph state machine + SQLite checkpointer
│   ├── incident_manager.py     # multi-incident handler
│   └── classifier.py           # natural language → scenario
│
├── sim_layer/
│   ├── map_state_manager.py    # batches GeoJSON, single writer to Mapbox
│   └── tracer.py               # Omium mock → real SDK swap
│
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── Map.jsx             # Mapbox, drone tracks, markers, heatmap, risk rings
│       ├── AgentStream.jsx     # live reasoning display
│       ├── AdvisoryPanel.jsx   # Agent 3 output
│       └── DroneStatus.jsx     # fleet status + telemetry
│
├── main.py                     # starts everything
├── config.yaml                 # ports, model names, scenario paths
└── README.md
```

---

## V1 BUILD ORDER

### Stage 1 — Foundation (confirm before proceeding)
Goal: one drone moving, one agent reasoning, one tool call executing.

1. FastAPI running, WebSocket confirmed
2. World state with one marker
3. DroneModel tick running — one drone position updating
4. One drone icon moving on Mapbox map
5. base_agent.py loop working
6. One tool call (`fly_to`) executing against DroneModel

**Stop. Confirm all 6 before Stage 2.**

---

### Stage 2 — Agent 1 Complete
7. Agent 1 full tool set working
8. Drone flies to marker, gets sensor reading
9. Classification reported to orchestrator
10. Loiter pattern visible on map
11. Agent stream panel showing reasoning live

---

### Stage 3 — Agent 2 + Orchestrator
12. Orchestrator receives Agent 1 output
13. Incident manager selects swarm type from decision table
14. Agent 2 deployed with correct swarm config
15. Specialist drones visible on map
16. Zone findings written back to world state

---

### Stage 4 — Agent 3 + Full Loop
17. Ollama running locally, Agent 3 connected
18. Agent 3 receives combined report
19. Advisory panel rendering on operator screen
20. World event fires (fire grows), Agent 3 updates
21. Full end-to-end: marker → surveillance → swarm → advisory

---

### Stage 5 — Demo Polish
22. Second scenario working (minimum 2 of 5)
23. Multi-incident state tested
24. Omium real SDK swap
25. Demo script written and timed
26. Fallback recording made
27. README quickstart verified on clean run

---

## V2 DEFERRED (do not build now)

- ArduPilot SITL replacing DroneModel (same DroneInterface, one afternoon swap)
- JSBSim flight dynamics
- Full 5-scenario coverage
- Predictive collapse/spread modeling
- Human override controls
- Multi-incident parallel stacks fully tested
- Mobile operator interface

---

## KNOWN RISKS + MITIGATIONS

| Risk | Severity | Mitigation | Live fallback |
|---|---|---|---|
| Mapbox concurrent update glitch | Critical | MapStateManager batches all agent writes on 1s interval — no agent writes directly to Mapbox | Switch to Omium trace tab |
| Drone animation teleporting | Critical | requestAnimationFrame lerp 500ms, CSS heading rotation | Reduce active drone count |
| LangGraph fan-out race condition | High | Strict sub-key ownership — each agent writes only to `state.{its_key}` | SQLite checkpointer restores last clean state in 10s |
| Ollama slow on local hardware | Medium | Pre-load model before demo, use 8b not 70b | Cache last advisory, show spinner |
| Omium SDK auth failure | Low | Mock tracer.py is structurally identical | Show console trace in terminal |
