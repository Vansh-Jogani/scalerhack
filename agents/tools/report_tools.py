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
            "recommended_drone_count": {"type": "integer", "description": "Number of specialist drones recommended based on sensor analysis"},
            "notes": {"type": "string", "description": "Additional observations"},
        },
        "required": ["incident_type", "confidence", "affected_area_m2", "recommended_drone_count", "notes"],
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


def create_report_classification_handler(orchestrator, stream_callback=None, agent_id: str = "agent-1"):
    """Create report_classification handler. Writes to orchestrator state and emits stream events."""
    async def report_classification(
        incident_type: str,
        confidence: float,
        affected_area_m2: float,
        notes: str,
        recommended_drone_count: int = 3,
    ) -> dict:
        report = {
            "classification": incident_type,
            "confidence": confidence,
            "affected_area_m2": affected_area_m2,
            "recommended_drone_count": recommended_drone_count,
            "notes": notes,
        }
        with tracer.start_span("agent1.report_classification", classification=incident_type, confidence=confidence):
            orchestrator.receive_agent1_report(report)

        # Emit classification stream event
        if stream_callback:
            try:
                await stream_callback("agent_stream", {
                    "agent_id": agent_id,
                    "event": "classification",
                    "content": {
                        "incident_type": incident_type,
                        "confidence": confidence,
                        "affected_area_m2": affected_area_m2,
                    },
                })
                # Emit Assessment_Panel_Event for frontend overlay
                await stream_callback("assessment_panel", {
                    "agent_id": agent_id,
                    "incident_type": incident_type,
                    "confidence": confidence,
                    "affected_area_m2": affected_area_m2,
                    "recommended_drone_count": recommended_drone_count,
                })
            except Exception as e:
                import structlog as _sl
                _sl.get_logger().warning("classification_emit_error", error=str(e))

        return {
            "accepted": True,
            "orchestrator_state": orchestrator.state if hasattr(orchestrator, "state") else "unknown",
        }
    return report_classification


REQUEST_BACKUP_TOOL = {
    "name": "request_backup",
    "description": "Request deployment of a specialist swarm. Call when confirmed incident warrants specialist response.",
    "input_schema": {
        "type": "object",
        "properties": {
            "swarm_type": {
                "type": "string",
                "enum": ["fire", "structural_collapse", "flood", "industrial_hazard", "maritime_sar"],
                "description": "Specialist swarm configuration to deploy",
            },
            "urgency": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                "description": "Deployment urgency based on observed conditions",
            },
            "rationale": {
                "type": "string",
                "description": "Plain-language explanation for the request",
            },
            "estimated_casualties": {
                "type": "integer",
                "description": "Estimated persons at risk (0 if unknown)",
            },
        },
        "required": ["swarm_type", "urgency", "rationale", "estimated_casualties"],
    },
}

MAINTAIN_SURVEILLANCE_TOOL = {
    "name": "maintain_surveillance",
    "description": "Continue loitering without requesting backup. Use when situation is ambiguous or below deployment threshold.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why specialist deployment is not yet warranted",
            },
            "reassess_in_seconds": {
                "type": "integer",
                "description": "Seconds before automatic reassessment",
                "minimum": 10,
                "maximum": 300,
            },
        },
        "required": ["reason", "reassess_in_seconds"],
    },
}


def create_request_backup_handler(orchestrator):
    async def request_backup(**kwargs) -> dict:
        orchestrator.receive_agent1_decision({**kwargs, "name": "request_backup"})
        return {"status": "ok", "message": f"Backup request received: {kwargs.get('swarm_type')} swarm"}
    return request_backup


def create_maintain_surveillance_handler(orchestrator):
    async def maintain_surveillance(**kwargs) -> dict:
        orchestrator.receive_agent1_decision({**kwargs, "name": "maintain_surveillance"})
        return {"status": "ok", "message": f"Surveillance maintained. Reassess in {kwargs.get('reassess_in_seconds')}s"}
    return maintain_surveillance


ISSUE_ADVISORY_TOOL = {
    "name": "issue_advisory",
    "description": "Issue a structured advisory for first responders.",
    "input_schema": {
        "type": "object",
        "properties": {
            "situation_summary": {"type": "string"},
            "immediate_actions": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "exclusion_zones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "radius_m": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["lat", "lon", "radius_m", "reason"],
                },
            },
            "resource_requirements": {"type": "array", "items": {"type": "string"}},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
            "monitoring_status": {"type": "string"},
            "last_updated": {"type": "string"},
            "based_on": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string"},
                    "coverage_pct": {"type": "number"},
                },
                "required": ["incident_id", "coverage_pct"],
            },
        },
        "required": [
            "situation_summary", "immediate_actions", "exclusion_zones",
            "resource_requirements", "risk_flags", "monitoring_status",
            "last_updated", "based_on",
        ],
    },
}
