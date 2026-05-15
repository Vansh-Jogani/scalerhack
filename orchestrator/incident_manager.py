"""Multi-incident handler. Sits between orchestrator and agent stacks."""

import structlog

logger = structlog.get_logger()

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Incident:
    def __init__(self, marker: dict):
        self.marker = marker
        self.agent1 = None
        self.agent2 = None
        self.status = "pending"


class IncidentManager:
    """
    Orchestrator talks to IncidentManager.
    IncidentManager spins up isolated agent stacks per incident.
    Each incident has its own Agent 1 + Agent 2 + feeds into shared Agent 3.
    """

    def __init__(self):
        self.active_incidents: dict[str, Incident] = {}
        self.incident_queue: list[dict] = []

    def on_new_marker(self, marker: dict) -> str:
        """Register a new marker. Returns 'created', 'queued', or 'reassigned'."""
        marker_id = marker.get("id", "unknown")

        if not self.active_incidents:
            self.create_incident(marker)
            return "created"

        priority = self.assess_priority(marker)
        if priority == "higher":
            self.reassign_resources(marker)
            return "reassigned"
        else:
            self.queue_incident(marker)
            return "queued"

    def create_incident(self, marker: dict) -> Incident:
        incident = Incident(marker=marker)
        self.active_incidents[marker["id"]] = incident
        logger.info("incident_created", marker_id=marker["id"], type=marker.get("type"))
        return incident

    def assess_priority(self, new_marker: dict) -> str:
        """Compare new marker severity against current active incidents."""
        new_sev = SEVERITY_ORDER.get(new_marker.get("severity", "medium"), 1)
        max_active_sev = max(
            SEVERITY_ORDER.get(i.marker.get("severity", "medium"), 1)
            for i in self.active_incidents.values()
        )
        return "higher" if new_sev > max_active_sev else "lower"

    def reassign_resources(self, marker: dict) -> None:
        """Pause lower-priority incidents, start new high-priority one."""
        for incident in self.active_incidents.values():
            if incident.agent1:
                incident.agent1.stop()
            if incident.agent2:
                incident.agent2.stop()
            incident.status = "paused"
            self.incident_queue.append(incident.marker)
        self.active_incidents.clear()
        self.create_incident(marker)
        logger.info("resources_reassigned", new_marker_id=marker["id"])

    def queue_incident(self, marker: dict) -> None:
        self.incident_queue.append(marker)
        logger.info("incident_queued", marker_id=marker["id"], queue_depth=len(self.incident_queue))

    def complete_incident(self, marker_id: str) -> None:
        """Mark incident resolved and promote next queued if present."""
        if marker_id in self.active_incidents:
            del self.active_incidents[marker_id]
            logger.info("incident_completed", marker_id=marker_id)
        if self.incident_queue:
            next_marker = self.incident_queue.pop(0)
            self.create_incident(next_marker)
            logger.info("incident_promoted_from_queue", marker_id=next_marker["id"])

    def get_active(self) -> dict[str, Incident]:
        return self.active_incidents

    def get_queue_depth(self) -> int:
        return len(self.incident_queue)
