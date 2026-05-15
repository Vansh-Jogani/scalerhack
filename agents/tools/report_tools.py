"""Report tools for agent classification, annotation, and advisory outputs.

Tools:
  - report_classification (Agent 1 → orchestrator)
  - request_detailed_pass (Agent 1 → self)
  - zone_annotate (Agent 2 → state.map_layers)
  - survivor_marker (Agent 2 → state.map_layers)
  - report_findings (Agent 2 → orchestrator)
"""

from sim_layer.tracer import tracer

# ---------------------------------------------------------------------------
# Agent 1 tools
# ---------------------------------------------------------------------------

REPORT_CLASSIFICATION_TOOL = {
    "name": "report_classification",
    "description": "Report incident classification to the orchestrator. Call this after completing survey and confirming incident type from sensor data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_type": {
                "type": "string",
                "enum": ["fire", "structural_collapse", "flood", "industrial_hazard", "maritime_sar"],
                "description": "Classified disaster type",
            },
            "confidence": {"type": "number", "description": "Classification confidence 0.0-1.0"},
            "affected_area_m2": {"type": "number", "description": "Estimated affected area in square meters"},
            "notes": {"type": "string", "description": "Additional observations"},
        },
        "required": ["incident_type", "confidence", "affected_area_m2", "notes"],
    },
}

REQUEST_DETAILED_PASS_TOOL = {
    "name": "request_detailed_pass",
    "description": "Request another orbit at lower altitude for detailed inspection. Minimum altitude is 60m AGL.",
    "input_schema": {
        "type": "object",
        "properties": {
            "zone_lat": {"type": "number", "description": "Center latitude of the zone to inspect"},
            "zone_lon": {"type": "number", "description": "Center longitude of the zone to inspect"},
            "pass_altitude": {"type": "number", "description": "Altitude for the detailed pass in meters AGL (minimum 60m)"},
        },
        "required": ["zone_lat", "zone_lon", "pass_altitude"],
    },
}


def create_report_classification_handler(orchestrator):
    """Create report_classification handler. Writes to orchestrator state."""
    async def report_classification(incident_type: str, confidence: float, affected_area_m2: float, notes: str) -> dict:
        report = {
            "classification": incident_type,
            "confidence": confidence,
            "affected_area_m2": affected_area_m2,
            "notes": notes,
        }
        with tracer.start_span("agent1.report_classification", classification=incident_type, confidence=confidence):
            orchestrator.receive_agent1_report(report)
        return {
            "accepted": True,
            "orchestrator_state": orchestrator.state if hasattr(orchestrator, "state") else "unknown",
        }
    return report_classification


def create_request_detailed_pass_handler(world_state, drone_id: str):
    """Create request_detailed_pass handler. Commands the drone for a lower-altitude orbit."""
    async def request_detailed_pass(zone_lat: float, zone_lon: float, pass_altitude: float) -> dict:
        # SPEC.md rule: never descend below 60m AGL
        if pass_altitude < 60.0:
            return {
                "dispatched": False,
                "message": "Altitude below 60m AGL is not permitted per operating rules.",
            }
        success = world_state.command_drone(drone_id, zone_lat, zone_lon, pass_altitude)
        if success:
            return {
                "dispatched": True,
                "drone_id": drone_id,
                "pass_altitude": pass_altitude,
            }
        return {"dispatched": False, "message": f"Drone {drone_id} not found"}
    return request_detailed_pass


# ---------------------------------------------------------------------------
# Agent 2 tools
# ---------------------------------------------------------------------------

ZONE_ANNOTATE_TOOL = {
    "name": "zone_annotate",
    "description": "Annotate a zone with a classification label and confidence. Writes to map layers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "zone_id": {"type": "string", "description": "Zone ID in format ZONE-{description}"},
            "label": {"type": "string", "description": "Classification label for the zone"},
            "confidence": {"type": "number", "description": "Confidence level 0.0-1.0"},
        },
        "required": ["zone_id", "label", "confidence"],
    },
}

SURVIVOR_MARKER_TOOL = {
    "name": "survivor_marker",
    "description": "Mark a detected survivor location on the map with estimated count.",
    "input_schema": {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude of detected survivors"},
            "lon": {"type": "number", "description": "Longitude of detected survivors"},
            "count": {"type": "integer", "description": "Estimated number of survivors at this location"},
        },
        "required": ["lat", "lon", "count"],
    },
}

REPORT_FINDINGS_TOOL = {
    "name": "report_findings",
    "description": "Report specialist swarm findings to orchestrator. Call after completing zone assessment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "zones_assessed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string"},
                        "label": {"type": "string"},
                        "confidence": {"type": "number"},
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    },
                    "required": ["zone_id", "label", "confidence", "risk_level"],
                },
            },
            "survivor_detections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "count": {"type": "integer"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["lat", "lon", "count", "confidence"],
                },
            },
            "hazard_markers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "type": {"type": "string"},
                        "exclusion_radius_m": {"type": "number"},
                    },
                    "required": ["lat", "lon", "type", "exclusion_radius_m"],
                },
            },
            "coverage_pct": {"type": "number", "description": "Percentage of area covered 0-100"},
            "notes": {"type": "string"},
        },
        "required": ["zones_assessed", "survivor_detections", "hazard_markers", "coverage_pct", "notes"],
    },
}


def create_zone_annotate_handler():
    """Create zone_annotate handler. Returns annotation for state.map_layers."""
    async def zone_annotate(zone_id: str, label: str, confidence: float) -> dict:
        annotation = {
            "zone_id": zone_id,
            "label": label,
            "confidence": confidence,
        }
        return {"status": "ok", "annotation": annotation}
    return zone_annotate


def create_survivor_marker_handler():
    """Create survivor_marker handler. Fires Omium span."""
    async def survivor_marker(lat: float, lon: float, count: int) -> dict:
        with tracer.start_span("agent2.survivor_marker", lat=lat, lon=lon, count=count):
            marker = {"lat": lat, "lon": lon, "count": count}
        return {"status": "ok", "marker": marker}
    return survivor_marker


def create_report_findings_handler(orchestrator):
    """Create report_findings handler. Writes to orchestrator."""
    async def report_findings(**kwargs) -> dict:
        orchestrator.receive_agent2_report(kwargs)
        return {"status": "ok", "message": "Findings reported to orchestrator"}
    return report_findings
