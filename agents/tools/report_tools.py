"""Report tools for agent classification and advisory outputs."""


REPORT_CLASSIFICATION_TOOL = {
    "name": "report_classification",
    "description": "Report incident classification to the orchestrator. Call this after completing survey and confirming incident type from sensor data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string", "description": "Incident ID in format INC-{timestamp}"},
            "classification": {
                "type": "string",
                "enum": ["fire", "structural_collapse", "flood", "industrial_hazard", "maritime_sar"],
                "description": "Classified disaster type",
            },
            "confidence": {"type": "number", "description": "Classification confidence 0.0-1.0"},
            "area": {
                "type": "object",
                "properties": {
                    "center": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                        },
                        "required": ["lat", "lon"],
                    },
                    "radius_m": {"type": "number"},
                },
                "required": ["center", "radius_m"],
            },
            "sensor_summary": {
                "type": "object",
                "properties": {
                    "thermal_detected": {"type": "boolean"},
                    "survivor_probability": {"type": "number"},
                    "hazard_flags": {"type": "array", "items": {"type": "string"}},
                    "wind_speed": {"type": "number"},
                    "visibility_m": {"type": "number"},
                },
                "required": ["thermal_detected", "survivor_probability", "hazard_flags", "wind_speed", "visibility_m"],
            },
            "recommended_swarm": {
                "type": "string",
                "description": "Not used by Agent 1 — leave empty, orchestrator selects",
            },
            "notes": {"type": "string", "description": "Additional observations"},
        },
        "required": ["incident_id", "classification", "confidence", "area", "sensor_summary", "notes"],
    },
}


def create_report_classification_handler(orchestrator):
    async def report_classification(**kwargs) -> dict:
        orchestrator.receive_agent1_report(kwargs)
        return {"status": "ok", "message": "Classification reported to orchestrator"}
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
