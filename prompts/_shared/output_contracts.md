Output contracts (enforced at API boundary):

Agent 1 — report_classification required fields:
  incident_id, classification, confidence (0–1), area.center.lat,
  area.center.lon, area.radius_m, sensor_summary, notes

Agent 2 — report_findings required fields:
  incident_id, zones_assessed[].zone_id, zones_assessed[].risk_level,
  survivor_detections[].confidence (0–1), coverage_pct (0–100)

Agent 3 — issue_advisory required fields:
  situation_summary, immediate_actions (max 5), exclusion_zones[],
  resource_requirements[], risk_flags[], monitoring_status, last_updated, based_on

Agent 4 — coordinate_relief required fields:
  incident_id, relief_type, actions[].priority, actions[].action,
  drone_waypoints[].lat, drone_waypoints[].lon, alerts[], resource_requests[], status
