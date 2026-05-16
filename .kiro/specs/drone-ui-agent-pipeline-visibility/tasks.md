# Tasks: Drone UI + Agent Pipeline Visibility

## Task List

- [x] 1. Create DroneDotLayer.js — Mapbox GeoJSON circle layer replacing DroneManager
  - [x] 1.1 Create `scalerhack/frontend/src/DroneDotLayer.js` with `init(map)`, `updateDrone(payload)`, and `destroy()` methods
  - [x] 1.2 In `init`, add `drones-source` (GeoJSON FeatureCollection), `drones-dot` circle layer, and `drones-label` symbol layer to the map
  - [x] 1.3 In `updateDrone`, upsert the drone feature in the internal map, compute `dot_color` from `DRONE_STATES` in `constants.js`, and call `source.setData()` with the full FeatureCollection
  - [x] 1.4 Register a click handler on `drones-dot` that opens a Mapbox popup with drone_id, state, battery_pct, alt, speed
  - [x] 1.5 In `destroy`, remove layers and source from the map

- [x] 2. Wire DroneDotLayer into Map.jsx and MapStateManager.js
  - [x] 2.1 In `Map.jsx`, replace the `DroneManager` import with `DroneDotLayer` and update the `MapStateManager.init` call to pass `DroneDotLayer`
  - [x] 2.2 In `MapStateManager.js`, replace the `DroneManager.updateDrone` call with `DroneDotLayer.updateDrone` (the interface is identical)

- [x] 3. Remove rotary drone HTML markers from DispatchAnimation.js
  - [x] 3.1 In `DispatchAnimation._phase5_burst`, remove the loop that creates rotary drone HTML markers (`droneEls`, `droneMarkers`) and their per-drone trail sources/layers
  - [x] 3.2 Remove `_phase6_patrol` drone orbit loop (the `_advanceFwOrbit` call for the fixed-wing can remain)
  - [x] 3.3 Ensure `stop()` cleanup no longer references removed drone marker arrays

- [x] 4. Add deriveOrchestratorState and deriveActiveAgent helper functions
  - [x] 4.1 Add `deriveOrchestratorState(entries)` pure function to `CommandDashboard.jsx` — scans entries newest-first, returns matching OrchestratorState string or `'STANDBY'`
  - [x] 4.2 Add `deriveActiveAgent(entries)` pure function to `CommandDashboard.jsx` — returns `entries[0].agent` or `null`

- [x] 5. Create OrchestratorHUD sub-component
  - [x] 5.1 Add `OrchestratorHUD({ orchestratorState, activeAgent })` component inside `CommandDashboard.jsx`
  - [x] 5.2 Render orchestrator state badge with color from the state→color mapping table in the design
  - [x] 5.3 Render agent pipeline flow `A1 ──▶ A2 ──▶ A3` with active agent highlighted (colored border + glow) and inactive agents at opacity 0.35
  - [x] 5.4 Apply 150ms CSS transition on the active agent highlight

- [x] 6. Integrate OrchestratorHUD into CommandDashboard pipeline tab
  - [x] 6.1 In `CommandDashboard`, derive `orchestratorState` and `activeAgent` from `entries` using the new helper functions on each render
  - [x] 6.2 Render `<OrchestratorHUD>` at the top of the pipeline tab content, above the feed scroll area

- [x] 7. Update pipeline feed content truncation
  - [x] 7.1 In the pipeline feed entry renderer in `CommandDashboard`, truncate `content` strings longer than 120 characters with `…`

- [x] 8. Verify no backend files were modified
  - [x] 8.1 Confirm no changes exist in `scalerhack/agents/`, `scalerhack/orchestrator/`, `scalerhack/sim/`, or `scalerhack/main.py`
