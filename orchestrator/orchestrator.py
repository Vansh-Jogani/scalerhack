"""ARIA Orchestrator — deterministic state machine.

Receives GO signal from operator, holds full context (area + disaster_type),
forwards only coordinates to Agent 1.
"""

import structlog

logger = structlog.get_logger()


class ARIAOrchestrator:
    states = [
        "STANDBY",
        "SURVEILLANCE_ACTIVE",
        "SWARM_ACTIVE",
        "ADVISORY_ACTIVE",
        "MULTI_INCIDENT",
        "EMERGENCY",
    ]

    def __init__(self, world_state, sensor_overlay=None):
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.state = "STANDBY"
        self.active_incident = None
        self.agent1 = None
        self.agent2 = None
        self.agent3 = None

    def receive_go_signal(self, payload: dict) -> dict:
        """Process GO signal from operator.

        Stores full area context (center, radius_m, boundary_polygon, disaster_type).
        Configures sensor overlay with boundary polygon.
        Returns the stripped payload for Agent 1 (coordinates only).
        """
        area = payload["area"]
        disaster_type = payload.get("disaster_type", "unknown")

        self.active_incident = {
            "area": area,
            "disaster_type": disaster_type,
        }

        if self.sensor_overlay and "boundary_polygon" in area:
            self.sensor_overlay.set_incident(area["boundary_polygon"], disaster_type)

        self.state = "SURVEILLANCE_ACTIVE"

        agent1_payload = {
            "action": "go",
            "coordinates": area["center"],
        }

        logger.info(
            "go_signal_processed",
            state=self.state,
            disaster_type=disaster_type,
            center=area["center"],
        )

        return agent1_payload

    def get_incident_context(self) -> dict | None:
        """Return full incident context (used by sensor overlay, not agents)."""
        return self.active_incident

    def receive_agent1_report(self, report: dict):
        """Receive classification report from Agent 1."""
        self.agent1_report = report
        logger.info("agent1_report_received", classification=report.get("classification"), confidence=report.get("confidence"))

    def receive_agent2_report(self, report: dict):
        """Receive findings report from Agent 2."""
        self.agent2_report = report
        logger.info("agent2_report_received", incident_id=report.get("incident_id"), coverage=report.get("coverage_pct"))
