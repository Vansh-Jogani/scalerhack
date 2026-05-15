# ARIA v1 — Frontend

Autonomous Response Intelligence Architecture — tactical operator dashboard for a multi-agent drone swarm simulation. Renders a live Mapbox map of Hyderabad alongside a three-panel right dashboard: incident command, agent pipeline feed, and AI advisory output.

---

## Stack

| Package | Version | Role |
|---|---|---|
| React | 18.3 | UI framework |
| Vite | 5.4 | Dev server + bundler |
| Mapbox GL JS | 3.4 | Map renderer |
| framer-motion | 11.0 | Advisory panel stagger animations |

No other runtime dependencies. No state management library. No router.

---

## Running

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # production bundle → dist/
```

Requires a `.env` file at `frontend/.env`:
```
VITE_MAPBOX_TOKEN=pk.eyJ1...your_token_here
```

The dev server proxies `/ws/*` to the backend. If the backend is not running, the map still loads and the UI is fully interactive — WebSocket panels just show "AWAITING BACKEND CONNECTION".

---

## Layout

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   MAP (60% width)            │  RIGHT PANEL (40% width)         │
│                              │                                   │
│   Mapbox dark-v11            │  ┌─────────────────────────────┐ │
│   center: Hyderabad          │  │  INCIDENT COMMAND (33%)     │ │
│   [78.4867, 17.3850]         │  │  AdminPanel.jsx             │ │
│   zoom: 12                   │  └─────────────────────────────┘ │
│                              │  ┌─────────────────────────────┐ │
│   Overlays (map-relative):   │  │  AGENT PIPELINE (33%)       │ │
│   • ARIA wordmark + status   │  │  AgentFeed.jsx              │ │
│   • Incident type badges     │  └─────────────────────────────┘ │
│   • Lat/lon coordinate HUD   │  ┌─────────────────────────────┐ │
│   • Assessment panel (anim)  │  │  ADVISORY [AGENT 3] (33%)   │ │
│                              │  │  AdvisoryPanel.jsx          │ │
│                              │  └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
frontend/src/
├── main.jsx                  React entry point
├── index.css                 Design system (CSS variables, keyframes, component classes)
├── constants.js              Single source of truth for all colours, labels, types, data
├── App.jsx                   Root component, WebSocket hooks, layout
│
├── Map.jsx                   Mapbox map + all map layer logic
├── AdminPanel.jsx            Incident command UI (draw zone, deploy)
├── AgentFeed.jsx             Agent event stream (WS + CustomEvent)
├── AdvisoryPanel.jsx         Agent 3 structured advisory output
│
├── MapStateManager.js        Singleton batch-writer to Mapbox (1 s flush)
├── DroneManager.js           Backend-driven drone icons (rAF lerp, trail)
├── DispatchAnimation.js      Scripted two-agent dispatch animation
│
└── data/
    └── response_centres.json 17 verified Hyderabad response centres
```

---

## Design System

All tokens are CSS custom properties in `index.css`.

### Colours

| Variable | Value | Use |
|---|---|---|
| `--bg` | `#0A0E14` | Page background |
| `--surface` | `#111822` | Panel backgrounds |
| `--surface-2` | `#1A2535` | Inset areas, code blocks |
| `--border` | `#243044` | Dividers, panel borders |
| `--text-primary` | `#E8EDF5` | Main text |
| `--text-secondary` | `#7A8FA8` | Labels, secondary |
| `--success` | `#00FF88` | NOMINAL status, FLYING state |
| `--warning` | `#FFB800` | ACTIVE status, LOITERING state |
| `--critical` | `#FF3B3B` | EMERGENCY status, RTL state |

### Disaster type colours

| Type key | Colour |
|---|---|
| `fire` / `FIRE` | `#FF4500` |
| `structural_collapse` | `#FF8C00` |
| `flood` | `#00BFFF` |
| `industrial_hazard` | `#ADFF2F` |
| `maritime_sar` | `#00CED1` |

These colours are used consistently for: incident pins, risk zone rings, drawn circle, dispatch animation trails, drone icons, and assessment panel borders.

### Typography

| Variable | Font | Used for |
|---|---|---|
| `--font-display` | Rajdhani | Panel headers, buttons, labels |
| `--font-mono` | JetBrains Mono | Coordinate HUD, agent feed, advisory content |
| `--font-body` | DM Sans | General body text |

---

## Map (`Map.jsx`)

The Mapbox map is the primary output surface. It owns all layer management through three sub-systems and several named exports.

### Map initialisation

- Style: `mapbox://styles/mapbox/dark-v11`
- Center: `[78.4867, 17.3850]` (Hyderabad)
- Zoom: `12`
- Attribution: compact, bottom-right

### Layers (added at load time, persistent)

| Source ID | Layer ID | Type | Purpose |
|---|---|---|---|
| `draw-circle-source` | `draw-circle-fill` | fill | Zone draw preview fill |
| `draw-circle-source` | `draw-circle-outline` | line | Zone draw dashed outline |
| `response-centres` | `response-centres-ring` | circle | Outer pulse ring around each centre |
| `response-centres` | `response-centres-dot` | circle | Filled dot, colour-coded by type |
| `response-centres` | `response-centres-label` | symbol | Name label, visible at zoom ≥ 13 |

### Zone draw mode

Activated by the DRAW ZONE button in AdminPanel. Two-click circle:

1. **Click 1** — places a white centre marker dot at the clicked coordinate.
2. **Mousemove** — live preview: draws a coloured dashed circle. Radius is clamped to `MAX_ZONE_RADIUS_M = 1000 m`.
3. **Click 2** — fixes the radius. Calls `onLocationSelect({ lat, lon, radius_m, vertices })` and exits draw mode. The circle stays on the map.

The circle colour tracks the currently selected disaster type in real time via the exported `setDrawColor(colour)` function.

### Named exports from `Map.jsx`

```js
import Map, { setDrawColor, clearDrawPolygon, responseCentres } from './Map.jsx'
```

| Export | Type | Purpose |
|---|---|---|
| `setDrawColor(colour)` | function | Update circle fill/outline colour live. Called by AdminPanel when disaster type changes. |
| `clearDrawPolygon()` | function | Remove the drawn circle and centre marker. Called by AdminPanel CLEAR button. |
| `responseCentres` | array | Re-export of the 17 response centre objects. Available for agent nearest-centre computation without a second JSON import. |

### Overlays (React, map-relative)

- **Top-left**: ARIA wordmark + system status badge (`NOMINAL` / `ACTIVE` / `EMERGENCY`)
- **Top-right**: Incident type counters (visible when at least one incident is active)
- **Bottom-left**: Live lat/lon coordinate readout, updates on mousemove

---

## MapStateManager (`MapStateManager.js`)

Singleton. The only authoritative writer to the persistent Mapbox layers driven by backend data. Nothing else calls `map.addLayer`, `map.addSource`, or `map.removeLayer` for backend-driven content.

### How it works

1. `MapStateManager.init(map, DroneManager, onIncidentAdd)` — called once after map load.
2. Incoming WebSocket messages are forwarded via `MapStateManager.receive(event)`.
3. Events accumulate in `_pendingUpdates[]` and are flushed every **1 second** in a single batch.
4. Each flushed event calls `_applyUpdate(event)` which switches on `action`.

### Supported actions

| `action` | Effect |
|---|---|
| `add_marker` | Creates a coloured SVG disaster pin at the incident location. Adds three risk zone rings (inner/mid/outer radii from `SEVERITY_RADII`). Calls `onIncidentAdd(incident_id, meta)`. |
| `update_marker` | Moves an existing disaster pin. |
| `remove_marker` | Removes the pin and all its risk zone layers. |
| `add_survivor` | Places a pulsing survivor pin (HTML marker). |
| `update_drone` | Delegates to `DroneManager.updateDrone(payload)`. |
| `update_layer` | Updates an arbitrary GeoJSON source by ID. |

### Risk zone radii (from `SEVERITY_RADII` in constants.js)

| Severity | Inner (m) | Mid (m) | Outer (m) |
|---|---|---|---|
| CRITICAL | 300 | 800 | 2000 |
| HIGH | 200 | 600 | 1500 |
| MEDIUM | 150 | 400 | 1000 |
| LOW | 100 | 250 | 600 |

### `onIncidentAdd` callback

When a new incident marker is added, MapStateManager fires the registered callback with `(incident_id, meta)` where `meta = { type, severity, lat, lon, status, timestamp }`. Map.jsx passes `_onIncidentAdd` here, which triggers the dispatch animation.

---

## DroneManager (`DroneManager.js`)

Singleton. Handles drone icons driven by live telemetry from the backend WebSocket. Runs its own continuous `requestAnimationFrame` loop independent of MapStateManager.

### Features

- **Smooth movement**: lerp over 500 ms (`LERP_MS`) — no teleporting.
- **Bearing**: computed from `atan2(dLon, dLat)`, updated only when displacement exceeds `1e-7°` to suppress loiter jitter.
- **Trail**: Mapbox LineString, last 20 positions (`TRAIL_MAX`), dashed, coloured to disaster type, 40% opacity.
- **State badge**: coloured dot below the icon reflecting drone state.
- **Click popup**: shows drone ID, state, battery %, altitude, speed.

### Drone states and colours

| State | Colour |
|---|---|
| FLYING | `#00FF88` |
| LOITERING | `#FFB800` |
| IDLE | `#7A8FA8` |
| THERMAL_SCAN | `#00BFFF` |
| RTL | `#FF3B3B` |

### `updateDrone(data)` payload

```js
{
  drone_id: string,
  lat: number,
  lon: number,
  heading: number,      // degrees
  state: string,        // FLYING | LOITERING | IDLE | THERMAL_SCAN | RTL
  battery_pct: number,
  alt: number,          // metres
  speed: number,        // m/s
  disaster_type: string // sets icon glow colour
}
```

---

## Dispatch Animation (`DispatchAnimation.js`)

A scripted, self-contained six-phase animation that plays immediately when an incident is deployed. It is independent of the backend — it runs from the moment `onIncidentAdd` fires on the frontend.

### Trigger flow

```
AdminPanel → POST /api/incident/create
           → Backend processes → sends ws add_marker event
           → App.jsx forwards to MapStateManager.receive()
           → MapStateManager._addDisasterPin() calls onIncidentAdd(id, meta)
           → Map.jsx _onIncidentAdd() fires DispatchAnimation
```

### Nearest centre resolution

```js
findNearestCentre([[meta.lon, meta.lat]], responseCentres)
```

Computes centroid of the polygon vertices (or single point), then returns the entry from `response_centres.json` with minimum Haversine distance. That centre's `[lon, lat]` becomes the drone departure point.

### Six-phase sequence

| Phase | Agent | Duration | What happens |
|---|---|---|---|
| 1 — Travel | ORCHESTRATOR | 2200 ms | Fixed-wing departs nearest response centre, easeInOut lerp to orbit entry point |
| 2 — Orbit | AGENT 1 | ~3800 ms (1.5 × 2π at 0.038 rad/frame) | Fixed-wing orbits ellipse centred on disaster zone |
| 3 — Assessment | AGENT 1 | 500 ms fade in, 2600 ms display | Panel appears top-right of map with zone analysis data |
| 4 — Dispatch | ORCHESTRATOR | 1900 ms (concurrent with phase 3) | Filled triangle arrow travels from response centre to zone centroid |
| 5 — Burst | AGENT 2 | 600–800 ms | Arrow disappears, two expanding ring pulses, N rotary drones spawn and fly to patrol positions |
| 6 — Patrol | AGENT 2 | continuous | N drones orbit patrol positions (CW/CCW alternating), fixed-wing continues high orbit at 50% opacity |

### Fixed-wing SVG (top-down silhouette)

```svg
<svg width="34" height="32" viewBox="-17 -16 34 32">
  <polygon points="0,-13 -17,3 -9,8 -2,5 -5,15 0,12 5,15 2,5 9,8 17,3"
           fill="[DISASTER_COLOUR]" stroke="rgba(255,255,255,0.55)" stroke-width="0.8"/>
  <circle cx="0" cy="-8" r="2.5" fill="white"/>
</svg>
```

### Rotary drone SVG (patrol drones)

```svg
<svg width="28" height="28" viewBox="0 0 28 28">
  <!-- Arms -->
  <line x1="14" y1="14" x2="20" y2="8"  stroke="white" stroke-width="1.5"/>
  <line x1="14" y1="14" x2="8"  y2="8"  stroke="white" stroke-width="1.5"/>
  <line x1="14" y1="14" x2="20" y2="20" stroke="white" stroke-width="1.5"/>
  <line x1="14" y1="14" x2="8"  y2="20" stroke="white" stroke-width="1.5"/>
  <!-- Rotors (filled, disaster colour) -->
  <circle cx="20" cy="8"  r="4" fill="[DISASTER_COLOUR]" stroke="white" stroke-width="0.5"/>
  <circle cx="8"  cy="8"  r="4" fill="[DISASTER_COLOUR]" stroke="white" stroke-width="0.5"/>
  <circle cx="20" cy="20" r="4" fill="[DISASTER_COLOUR]" stroke="white" stroke-width="0.5"/>
  <circle cx="8"  cy="20" r="4" fill="[DISASTER_COLOUR]" stroke="white" stroke-width="0.5"/>
  <!-- Body + state dot -->
  <circle cx="14" cy="14" r="4" fill="white"/>
  <circle cx="14" cy="14" r="2.5" fill="[STATE_COLOUR]"/>  <!-- #00FF88 during patrol -->
</svg>
```

### Orbit geometry

- Orbit is an ellipse centred on the zone centroid.
- `Rx = 0.0014°` (longitude radius, ≈ 140 m), `Ry = Rx × 0.7 = 0.00098°` (latitude radius, flattened for visual perspective).
- Orbit entry angle: `atan2((src.lat - dst.lat) / Ry, (src.lon - dst.lon) / Rx)` — the parametric angle on the ellipse closest to the response centre.
- Fixed-wing heading at angle `a`: `atan2(cos(a) × Ry, -sin(a) × Rx) + π/2` — the tangent to the ellipse.

### Patrol geometry

```
patrol_angle_i = (i / N) × 2π + random(-0.2, 0.2)
patrol_lon_i   = centroid.lon + cos(angle_i) × 0.0006°
patrol_lat_i   = centroid.lat + sin(angle_i) × 0.0006°
```

Each drone orbits its patrol centre at radius `0.00016°`, advancing `±0.04 rad/frame` (CW for even index, CCW for odd).

### Mapbox layers created by animation

All are prefixed `fw-` (Agent 1) or `dispatch-` (Agent 2) and removed atomically on `.stop()`.

| Layer ID | Type | Content |
|---|---|---|
| `fw-trail` | line | Fixed-wing flight path, dashed, last 90 pts |
| `dispatch-trail` | line | Arrow flight path, dashed, last 60 pts |
| `dispatch-burst-ring-1/2` | circle | Expanding burst rings at centroid |
| `dispatch-drone-trail-{i}` | line | Per-drone patrol trail, last 20 pts, 35% opacity |

### Agent event firing

At each phase transition, `DispatchAnimation.js` fires a `CustomEvent` on `window`:

```js
window.dispatchEvent(new CustomEvent('aria-agent-event', {
  detail: { agent: 'ORCHESTRATOR' | 'AGENT_1' | 'AGENT_2', text: '...' }
}))
```

| Phase | Agent | Message |
|---|---|---|
| 1 start | ORCHESTRATOR | `SURVEILLANCE_ACTIVE — Agent 1 dispatched · fixed-wing en route` |
| 2 start | AGENT_1 | `On station — thermal scan active · orbiting zone` |
| 3 show | AGENT_1 | `Classification: [type] · confidence 94% · [N] drones required` |
| 4 start | ORCHESTRATOR | `SWARM_ACTIVE — Agent 2 deploying [N] response drones` |
| 5 start | AGENT_2 | `Swarm on target — establishing patrol pattern` |
| 6 start | AGENT_2 | `Zone coverage active · [N] drones monitoring` |

### API

```js
// Constructor
new DispatchAnimation(mapInstance, {
  srcGeo:        { lat, lon },   // response centre
  dstGeo:        { lat, lon },   // zone centroid
  droneCount:    number,
  disasterColour: string,         // hex
  disasterType:  string,          // lowercase e.g. 'fire'
})

anim.start()         // begins phase 1
anim.stop()          // cancels all animation, removes all Mapbox layers/sources/markers
anim.onComplete(cb)  // callback fired when phase 6 (patrol) begins
```

### Exported helpers

```js
import DispatchAnimation, {
  haversine,           // (lat1, lon1, lat2, lon2) → metres
  findNearestCentre,   // (polygonVertices, responseCentres) → centre object
  calcBearing,         // (srcLng, srcLat, dstLng, dstLat) → radians
  geoToPixel,          // (map, lng, lat) → { x, y } pixel coords
} from './DispatchAnimation.js'
```

---

## Response Centres (`data/response_centres.json`)

17 real Hyderabad disaster response centres. This file is the **authoritative source** for drone staging locations. The nearest centre to any incident centroid is resolved at runtime via Haversine distance.

### Schema

```json
{
  "id":       "hyd-fs-secunderabad",
  "name":     "Secunderabad Fire Station",
  "type":     "FIRE_STATION",
  "lat":      17.4428,
  "lon":      78.4880,
  "address":  "1-7-43/46, Sardar Patel Road, Secunderabad, 500003",
  "verified": true
}
```

`verified: false` means the coordinates are neighbourhood-approximate (not GPS-confirmed). These entries render at 50% opacity on the map.

### Type → colour mapping on map

| Type | Map colour |
|---|---|
| FIRE_STATION | `#4FC3F7` (light blue) |
| NDRF | `#1565C0` (dark blue) |
| SDRF | `#1E88E5` (blue) |
| HOSPITAL | `#E53935` (red) |
| POLICE | `#5E35B1` (purple) |
| CIVIL_DEFENCE | `#00897B` (teal) |
| AIRPORT_EMERGENCY | `#F4511E` (deep orange) |
| MUNICIPAL_EMERGENCY | `#039BE5` (cyan) |

Each centre renders as three Mapbox layers: an outer ring (stroke only, lower opacity for unverified), a filled dot, and a text label that appears at zoom ≥ 13. Clicking a dot opens a popup showing name, type, address, and an "coords approximate" warning for unverified entries.

### Centres included

| Name | Type | Verified |
|---|---|---|
| Secunderabad Fire Station | FIRE_STATION | ✓ |
| Film Nagar Fire Station | FIRE_STATION | ✓ |
| Sanath Nagar Fire Station | FIRE_STATION | ✓ |
| Moghalpura Fire Station | FIRE_STATION | ✓ |
| High Court Fire Station | FIRE_STATION | ✓ |
| Kukatpally Fire Station | FIRE_STATION | ✓ |
| Madhapur Fire Station | FIRE_STATION | ✓ |
| NDRF 10th Battalion Forward Base | NDRF | ✓ |
| Telangana SDRF State Emergency Operations | SDRF | ✓ |
| Apollo Hospitals Jubilee Hills | HOSPITAL | ✓ |
| Osmania General Hospital | HOSPITAL | — |
| Nizam's Institute of Medical Sciences | HOSPITAL | — |
| Telangana ICCC Emergency Control Room | POLICE | ✓ |
| Hyderabad Police Commissioner's Office | POLICE | — |
| GHMC Disaster Management Cell | MUNICIPAL_EMERGENCY | ✓ |
| RGIA Airport Emergency Services | AIRPORT_EMERGENCY | ✓ |
| Telangana Civil Defence District HQ | CIVIL_DEFENCE | — |

---

## AdminPanel (`AdminPanel.jsx`)

The incident command UI. No backend data flows through it — it is purely operator input.

### Controls

1. **DRAW ZONE** — toggles zone draw mode on the map. Button label changes to `◎ DRAWING...` while active.
2. **CLEAR** — visible once a zone is drawn. Removes the circle from the map and resets captured coordinates.
3. **Zone summary** — shows once a zone is drawn: centroid lat/lon and radius (in metres below 1 km, km above).
4. **Disaster type pills** — FIRE / STRUCTURAL / FLOOD / INDUSTRIAL / MARITIME SAR. Selecting one updates the circle colour live.
5. **Severity buttons** — LOW / MEDIUM / HIGH / CRITICAL.
6. **DEPLOY INCIDENT** — enabled only when zone + type + severity are all set. Posts to `/api/incident/create`.

### Deploy payload

```json
{
  "lat":           17.385,
  "lon":           78.4867,
  "type":          "fire",
  "severity":      "high",
  "zone_radius_m": 650,
  "zone_polygon":  [[lng, lat], ...]   // 65 vertices (64 steps + close)
}
```

### Deploy response states

| State | UI |
|---|---|
| `idle` | DEPLOY INCIDENT (greyed if not ready, coloured if ready) |
| `dispatching` | spinner + DISPATCHING... |
| `active` | ✓ INCIDENT ACTIVE (4 s, then idle) |
| `failed` | ✕ DEPLOY FAILED (3 s, then idle) |

---

## AgentFeed (`AgentFeed.jsx`)

Live event stream from the agent pipeline. Consumes two sources simultaneously:

### 1. WebSocket `/ws/agents`

Expects messages of the form:
```json
{
  "type":        "agent_event",
  "agent":       "ORCHESTRATOR" | "AGENT_1" | "AGENT_2" | "AGENT_3",
  "timestamp":   "14:32:05",
  "text":        "event message",
  "incident_id": "inc-abc123"
}
```

Reconnects with exponential backoff: `[1, 2, 4, 8, 30]` seconds.

### 2. `aria-agent-event` CustomEvent (frontend-only)

Fired by `DispatchAnimation.js` at each animation phase transition. Received by:

```js
window.addEventListener('aria-agent-event', (e) => {
  // e.detail = { agent, text }
  addEntry({ agent, text, timestamp: HH:MM:SS, ... })
})
```

This means agent feed entries appear during the animation even when the backend is not running.

### Display

- Max 200 entries. New entries prepend (newest at top).
- Each entry coloured by agent:

| Agent | Accent colour |
|---|---|
| ORCHESTRATOR | none (plain border) |
| AGENT_1 | `#7B68EE` (medium slate blue) |
| AGENT_2 | disaster type colour of active incident |
| AGENT_3 | `#00FF88` (green) |

- AGENT_3 text is also forwarded to `AdvisoryPanel` via the `onAdvisoryUpdate` prop.
- Connection status shown in panel header: `● LIVE` (green) or `○ CONNECTING` (amber).

---

## AdvisoryPanel (`AdvisoryPanel.jsx`)

Parses and renders structured output from Agent 3. Expects a multi-line string with section headers in the form `SECTION NAME: content`.

### Recognised sections (in display order)

| Section | Display style |
|---|---|
| SITUATION SUMMARY | body paragraph |
| IMMEDIATE ACTIONS | numbered monospace list |
| EXCLUSION ZONES | bulleted list, critical-colour border |
| RESOURCE REQUIREMENTS | body paragraph |
| RISK FLAGS | bulleted list, warning-colour border |
| MONITORING | secondary-colour body paragraph |

Sections not present in the advisory are omitted. When a new advisory arrives, all sections animate in with `framer-motion`: `opacity 0→1`, `y 8→0`, staggered at 80 ms per section.

---

## WebSocket Protocol

The frontend connects to two WebSocket endpoints. Both use the same exponential backoff reconnect strategy.

### `/ws/map` — Map state events

Handled by `App.jsx` → forwarded to `MapStateManager.receive()`.

```json
{
  "type":        "map_update",
  "action":      "add_marker" | "update_marker" | "remove_marker" | "add_survivor" | "update_drone" | "update_layer",
  "incident_id": "inc-abc123",
  "payload": {
    "lat":      17.385,
    "lon":      78.4867,
    "type":     "fire",
    "severity": "high",
    "status":   "ACTIVE"
  }
}
```

Also handles legacy formats:
- `type: "telemetry"` — forwarded as `update_drone` action.
- `type: "markers"` — array of marker objects, each forwarded as `add_marker`.

### `/ws/agents` — Agent pipeline events

Handled directly by `AgentFeed.jsx`.

```json
{
  "type":        "agent_event",
  "agent":       "AGENT_1",
  "timestamp":   "14:32:05",
  "text":        "Thermal scan complete — 3 heat signatures confirmed",
  "incident_id": "inc-abc123"
}
```

---

## Backend API Contract

The frontend makes exactly one HTTP request:

### `POST /api/incident/create`

```json
// Request body
{
  "lat":           number,
  "lon":           number,
  "type":          "fire" | "structural_collapse" | "flood" | "industrial_hazard" | "maritime_sar",
  "severity":      "low" | "medium" | "high" | "critical",
  "zone_radius_m": number | null,
  "zone_polygon":  [[lon, lat], ...] | null   // 65 [lon, lat] pairs (GeoJSON order)
}

// Expected: 200 OK on success, any non-2xx treated as failure
// Response body is not read by the frontend
```

The backend is expected to subsequently broadcast a `map_update / add_marker` event over `/ws/map` containing the incident's lat, lon, type, and severity. This is what triggers the map pin, risk zones, and dispatch animation.

---

## System Status Derivation

`App.jsx` derives system status from the active incident set:

| Condition | Status | Colour |
|---|---|---|
| No incidents | NOMINAL | `#00FF88` |
| Incidents with LOW or MEDIUM severity only | ACTIVE | `#FFB800` |
| Any incident with HIGH or CRITICAL severity | EMERGENCY | `#FF3B3B` |

Displayed in the ARIA wordmark overlay on the map.

---

## Known Gaps (backend not yet in sync)

The following frontend capabilities are fully built and ready but require backend implementation to activate:

- **`drone_count` in `add_marker` payload** — `DispatchAnimation` defaults to `droneCount: 3`. If the backend sends `payload.drone_count`, Map.jsx needs a one-line change to forward it.
- **`zone_polygon` in `add_marker` payload** — The deploy POST sends `zone_polygon` to the backend. If the backend echoes it in the ws event, `findNearestCentre` could use the full polygon centroid rather than the single `lat/lon` point.
- **`/ws/agents` stream** — AgentFeed is fully wired and reconnects automatically. Backend needs to push `agent_event` messages on this socket.
- **Agent 3 advisory format** — AdvisoryPanel expects section headers (`SITUATION SUMMARY:`, `IMMEDIATE ACTIONS:`, etc.) in the Agent 3 text output. If Agent 3 formats differently, `parseAdvisory()` in `AdvisoryPanel.jsx` needs updating.
- **Evac route rendering** — `MapStateManager.addEvacRoute(incident_id, coordinates)` is implemented and ready. No backend message currently triggers it. Send `action: "update_layer"` with a LineString GeoJSON to render evac routes.
- **Survivor pins** — `MapStateManager._addSurvivorPin(payload)` is implemented. Triggered by `action: "add_survivor"` on `/ws/map`.
