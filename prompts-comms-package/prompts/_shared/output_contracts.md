## Output contracts

### Agent 1 — report_classification

Call `report_classification()` with exactly these fields. No extras. No omissions.

| Field | Type | Notes |
|---|---|---|
| `incident_id` | string | format: `INC-{unix_timestamp}` |
| `classification` | enum | `fire`, `structural_collapse`, `flood`, `industrial_hazard`, `maritime_sar` |
| `confidence` | float | 0.0 – 1.0 |
| `area.center.lat` | float | |
| `area.center.lon` | float | |
| `area.radius_m` | float | orbit radius at which sensor data was confirmed |
| `sensor_summary.thermal_detected` | bool | |
| `sensor_summary.survivor_probability` | float | 0.0 – 1.0 |
| `sensor_summary.hazard_flags` | list[str] | empty list if none |
| `sensor_summary.wind_speed` | float | m/s |
| `sensor_summary.visibility_m` | float | meters |
| `notes` | string | additional observations, empty string if none |

---

### Agent 2 — report_swarm_findings

Call `report_swarm_findings()` with exactly these fields. No extras. No omissions.

| Field | Type | Notes |
|---|---|---|
| `incident_id` | string | from surveillance report |
| `zones_assessed` | list | one entry per zone surveyed |
| `zones_assessed[].zone_id` | string | format: `ZONE-{lat:.4f}-{lon:.4f}` |
| `zones_assessed[].lat` | float | |
| `zones_assessed[].lon` | float | |
| `zones_assessed[].findings.thermal_signatures` | int | count of thermal hits |
| `zones_assessed[].findings.structural_integrity` | float | 0.0 = collapsed, 1.0 = intact |
| `zones_assessed[].findings.hazards_detected` | list[str] | empty list if none |
| `zones_assessed[].findings.survivor_count` | int | confirmed or probable |
| `zones_assessed[].risk_level` | enum | `low`, `medium`, `high`, `critical` |
| `zones_assessed[].actionable` | bool | true only if high/critical AND sensor-confirmed |
| `survivor_detections` | list | immediate detections (mark_survivor already called) |
| `survivor_detections[].lat` | float | |
| `survivor_detections[].lon` | float | |
| `survivor_detections[].confidence` | float | 0.0 – 1.0 |
| `hazard_map` | list | all hazards (mark_hazard already called) |
| `hazard_map[].lat` | float | |
| `hazard_map[].lon` | float | |
| `hazard_map[].type` | string | |
| `hazard_map[].exclusion_radius_m` | float | |
| `coverage_pct` | float | 0 – 100, area covered |
| `notes` | string | constraint violations, anomalies, empty string if none |
