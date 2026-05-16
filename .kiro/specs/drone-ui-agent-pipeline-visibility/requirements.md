# Requirements: Drone UI + Agent Pipeline Visibility

## Requirement 1: Remove Drone Animation and Replace with Mapbox Dot Layer

### User Story
As a disaster response operator, I want drone positions shown as simple colored dots on the map so that the UI remains performant and readable during active incidents with multiple drones.

### Acceptance Criteria

1.1 `DroneManager.js` is replaced by `DroneDotLayer.js`. The new module manages a single Mapbox GeoJSON source (`drones-source`) and renders drones as circle layers — no HTML markers, no SVG, no `requestAnimationFrame` lerp loop.

1.2 `Map.jsx` initializes `DroneDotLayer` (not `DroneManager`) on map load, adding `drones-source`, `drones-dot`, and `drones-label` layers.

1.3 `MapStateManager.js` calls `DroneDotLayer.updateDrone(payload)` for `update_drone` actions, replacing the call to `DroneManager.updateDrone`.

1.4 The rotary drone HTML markers spawned in `DispatchAnimation._phase5_burst` are removed. The fixed-wing marker and dispatch arrow marker in `DispatchAnimation` are retained unchanged.

1.5 Clicking a drone dot on the map opens a Mapbox popup showing `drone_id`, `state`, `battery_pct`, `alt`, and `speed`.

1.6 Drone labels (`drone_id` text) appear below each dot at zoom level ≥ 13.

---

## Requirement 2: Drone Dot Color Encodes Agent-Commanded State

### User Story
As an operator, I want each drone dot's color to reflect the drone's current commanded state so that I can instantly assess fleet status at a glance.

### Acceptance Criteria

2.1 The `dot_color` property of each drone GeoJSON feature is set according to the following mapping, sourced from the existing `DRONE_STATES` constant in `constants.js`:

| State | Hex Color |
|---|---|
| `IDLE` | `#7A8FA8` |
| `FLYING` | `#00FF88` |
| `LOITERING` | `#FFB800` |
| `RTL` | `#FF3B3B` |
| `THERMAL_SCAN` | `#00BFFF` |

2.2 The Mapbox `drones-dot` layer uses a `['get', 'dot_color']` paint expression so color is driven by feature properties, not hardcoded in the layer spec.

2.3 If a telemetry payload arrives with an unrecognized `state` value, the dot renders with the `IDLE` fallback color (`#7A8FA8`).

2.4 Drones in `THERMAL_SCAN` state render with a slightly larger circle radius (9px) and a subtle blur (0.3) to visually distinguish active sensor sweeps.

2.5 Drones in `RTL` state render with a red dot (`#FF3B3B`) matching the existing `DRONE_STATES.RTL` constant.

---

## Requirement 3: Orchestrator State Visible in UI

### User Story
As an operator, I want to see the current orchestrator state (STANDBY, SURVEILLANCE_ACTIVE, SWARM_ACTIVE, ADVISORY_ACTIVE) in the command panel so that I understand what phase of the response pipeline is active.

### Acceptance Criteria

3.1 A new `OrchestratorHUD` sub-component is added to `CommandDashboard.jsx` and rendered above the pipeline feed, inside the "AGENT PIPELINE" tab.

3.2 `OrchestratorHUD` displays the current orchestrator state as a text badge. The badge color matches the state:

| State | Color |
|---|---|
| `STANDBY` | `#4A6A8A` |
| `SURVEILLANCE_ACTIVE` | `#7B68EE` |
| `SWARM_ACTIVE` | `#FFB800` |
| `ADVISORY_ACTIVE` | `#00FF88` |
| `MULTI_INCIDENT` | `#FF8C42` |
| `EMERGENCY` | `#FF3B3B` |

3.3 Orchestrator state is derived from the `entries` array in `CommandDashboard` using a pure `deriveOrchestratorState(entries)` function — no new WebSocket message types or backend changes.

3.4 `deriveOrchestratorState` scans entries newest-first and returns the first matching state. If no entries exist, it returns `'STANDBY'`.

3.5 The orchestrator state badge updates in real time as new `agent_stream` events arrive.

---

## Requirement 4: Active Agent Visible in UI

### User Story
As an operator, I want to see which agent (Agent 1, 2, or 3) is currently active so that I know which part of the pipeline is executing.

### Acceptance Criteria

4.1 `OrchestratorHUD` renders a visual agent pipeline flow: `A1 ──▶ A2 ──▶ A3`.

4.2 The active agent node (derived from the `agent_id` of the most recent `agent_stream` event) is highlighted with a colored border and glow matching `AGENT_COLORS` from `constants.js`.

4.3 Inactive agent nodes are rendered at reduced opacity (0.35).

4.4 When the active agent changes (e.g., Agent 1 hands off to Agent 2), the highlight transitions to the new agent node via a CSS opacity/border transition (150ms).

4.5 `deriveActiveAgent(entries)` returns the `agent` field of `entries[0]`, or `null` if entries is empty. This is a pure function.

---

## Requirement 5: Agent Stream Events Visible in Live Feed Panel

### User Story
As an operator, I want to see a live feed of agent reasoning, tool calls, and completions so that I can follow the AI pipeline's decision-making in real time.

### Acceptance Criteria

5.1 The existing pipeline feed in `CommandDashboard.jsx` continues to display `agent_stream` events as they arrive, with each row showing timestamp, agent label, event type, and content.

5.2 Each feed row is color-coded by agent using `AGENT_COLORS` from `constants.js` (Agent 1: `#7B68EE`, Agent 2: disaster color or `#FFB800`, Agent 3: `#00FF88`, Orchestrator: `#4A5568`).

5.3 Content strings longer than 120 characters are truncated with an ellipsis in the feed row display.

5.4 The feed auto-scrolls to the newest entry (top of the reversed list) when new events arrive.

5.5 The feed retains up to 150 entries (existing `MAX_ENTRIES` constant), dropping the oldest when the limit is exceeded.

---

## Requirement 6: Agent Handoff Visibility

### User Story
As an operator, I want to see when Agent 1 hands off to Agent 2 so that I know the surveillance phase has completed and the swarm deployment phase has begun.

### Acceptance Criteria

6.1 When an `agent_stream` event arrives with `agent_id: 'orchestrator'` and content containing `'SWARM_ACTIVE'`, the orchestrator state badge transitions to `SWARM_ACTIVE` and the active agent highlight moves to `A2`.

6.2 When an `agent_stream` event arrives with `agent_id: 'agent-2'`, the `A2` node in the pipeline flow is highlighted.

6.3 The pipeline feed shows a visually distinct row for orchestrator events (existing `orchestrator` CSS class behavior is preserved).

---

## Requirement 7: Drone Dots Appear When Agent 2 Deploys Drones

### User Story
As an operator, I want deployed drones to appear on the map as colored dots when Agent 2 deploys them so that I can track the swarm's positions.

### Acceptance Criteria

7.1 When the backend begins broadcasting `telemetry` messages for newly deployed drones, `DroneDotLayer.updateDrone` adds them to `drones-source` and they appear on the map as dots.

7.2 Each new drone appears with the color corresponding to its initial `state` (typically `FLYING` → `#00FF88`).

7.3 Drone dots update position in real time as subsequent `telemetry` messages arrive. Position updates are applied by calling `source.setData()` with the full updated `FeatureCollection`.

7.4 No drone HTML markers are created by `DispatchAnimation` during or after Agent 2's deployment phase.

---

## Requirement 8: Frontend-Only Changes

### User Story
As a developer, I want all changes confined to `scalerhack/frontend/src/` so that the backend remains stable and unmodified.

### Acceptance Criteria

8.1 No files in `scalerhack/agents/`, `scalerhack/orchestrator/`, `scalerhack/sim/`, or `scalerhack/main.py` are modified.

8.2 No new WebSocket message types are introduced. All UI state is derived from the existing `telemetry`, `agent_stream`, `markers`, and `advisory` message types.

8.3 No new npm packages are added. All implementation uses `mapbox-gl`, React, and existing project utilities.
