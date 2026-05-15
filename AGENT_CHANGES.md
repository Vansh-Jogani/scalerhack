# ARIA — Agent Modifications
Apply these changes only. Do not refactor anything else.
Confirm each change working before applying the next.

---

## CHANGE 1: God Mode Go Signal

The GO button sends this payload to the orchestrator:

```json
{
  "action": "go",
  "area": {
    "center": {"lat": float, "lon": float},
    "radius_m": float,
    "boundary_polygon": [[lat, lon], [lat, lon], "..."]
  },
  "disaster_type": str
}
```

Orchestrator passes to Agent 1:

```json
{
  "action": "go",
  "coordinates": {"lat": float, "lon": float}
}
```

Agent 1 never receives disaster_type or boundary_polygon.
Orchestrator holds both but does not forward them to Agent 1.

---

## CHANGE 2: Agent 1 — Survey Pattern

Agent 1 receives only a coordinate.
It must fly an expanding circle pattern centered on that coordinate
until sensor returns confirm the area.

Replace any single fly_to behavior with this logic:

1. Fly to coordinates
2. Begin expanding circle: radius 50m, then 100m, then 150m
3. At each orbit, call get_sensor_reading()
4. If sensor returns data → area found, continue orbiting at that radius
5. Once full orbit complete with consistent sensor data → classify
6. Call report_classification() with findings
7. Remain in loiter at confirmed radius

Do not change DroneModel or drone physics.
Only change Agent 1 tool execution logic.

---

## CHANGE 3: Sensor Overlay — Polygon Trigger

sensor_overlay.py currently triggers on distance to center point.
Change to point-in-polygon check.

When drone position is INSIDE boundary_polygon → return sensor data
When drone position is OUTSIDE boundary_polygon → return null

Use this check:

```python
def point_in_polygon(lat, lon, polygon):
    # Ray casting algorithm
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        if ((polygon[i][1] > lon) != (polygon[j][1] > lon) and
            lat < (polygon[j][0] - polygon[i][0]) *
            (lon - polygon[i][1]) /
            (polygon[j][1] - polygon[i][1]) + polygon[i][0]):
            inside = not inside
        j = i
    return inside
```

Do not change DroneModel. Only change sensor_overlay.py.

---

## CHANGE 4: Agent 1 Output Schema

Agent 1 report_classification() tool must produce exactly this.
No extra fields. No missing fields.

```json
{
  "incident_id": "INC-{timestamp}",
  "classification": "fire | structural_collapse | flood | industrial_hazard | maritime_sar",
  "confidence": 0.0,
  "area": {
    "center": {"lat": 0.0, "lon": 0.0},
    "radius_m": 0.0
  },
  "sensor_summary": {
    "thermal_detected": false,
    "survivor_probability": 0.0,
    "hazard_flags": [],
    "wind_speed": 0.0,
    "visibility_m": 0.0
  },
  "recommended_swarm": "from SWARM_CAPABILITIES keys only",
  "notes": ""
}
```

recommended_swarm is selected by orchestrator from SWARM_CAPABILITIES keys.
Agent 1 does not choose the swarm — it only reports classification.

---

## CHANGE 5: Agent 2 Output Schema

Agent 2 findings must produce exactly this per zone assessed.

```json
{
  "incident_id": "",
  "zones_assessed": [
    {
      "zone_id": "ZONE-{lat}-{lon}",
      "lat": 0.0,
      "lon": 0.0,
      "findings": {
        "thermal_signatures": 0,
        "structural_integrity": 0.0,
        "hazards_detected": [],
        "survivor_count": 0
      },
      "risk_level": "low | medium | high | critical",
      "actionable": false
    }
  ],
  "survivor_detections": [
    {"lat": 0.0, "lon": 0.0, "confidence": 0.0}
  ],
  "hazard_map": [
    {"lat": 0.0, "lon": 0.0, "type": "", "exclusion_radius_m": 0.0}
  ],
  "coverage_pct": 0.0,
  "notes": ""
}
```

---

## CHANGE 6: Agent 3 Input + Output

Agent 3 receives both reports combined:

```json
{
  "agent1_report": {},
  "agent2_report": {}
}
```

Agent 3 produces exactly this:

```json
{
  "situation_summary": "",
  "immediate_actions": [],
  "exclusion_zones": [
    {"lat": 0.0, "lon": 0.0, "radius_m": 0.0, "reason": ""}
  ],
  "resource_requirements": [],
  "risk_flags": [],
  "monitoring_status": "",
  "last_updated": "ISO timestamp",
  "based_on": {
    "incident_id": "",
    "coverage_pct": 0.0
  }
}
```

immediate_actions: numbered list, max 5 items.
Agent 3 updates this output every time a new trigger fires.

---

## APPLY ORDER

1. CHANGE 1 — verify GO signal reaches orchestrator correctly
2. CHANGE 3 — verify sensor overlay triggers on polygon entry
3. CHANGE 2 — verify Agent 1 flies survey pattern and gets sensor data
4. CHANGE 4 — verify Agent 1 output matches schema
5. CHANGE 5 — verify Agent 2 output matches schema
6. CHANGE 6 — verify Agent 3 receives both and produces advisory

Do not proceed to next change until current one is confirmed working.
Do not refactor any code outside the files mentioned in each change.
