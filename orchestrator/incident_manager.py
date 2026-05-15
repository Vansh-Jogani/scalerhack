"""Multi-incident handler. Sits between orchestrator and agent stacks.

V1 scope: create or queue incidents only.
No live resource reassignment (V2 DEFERRED per CONTEXT.md).
"""

import structlog

logger = structlog.get_logger()


class Incident:
    """Represents a single incident with its agent stack."""

    def __init__(self, marker: dict):
        self.marker = marker
        self.agent1 = None
        self.agent2 = None
        self.status = "pending"  # pending, active, complete
        self.agent1_report = None
        self.agent2_report = None


class IncidentManager:
    """Orchestrator talks to IncidentManager.

    IncidentManager spins up isolated agent stacks per incident.
    Each incident has its own Agent 1 + Agent 2 + feeds into shared Agent 3.

    V1: create-or-queue only. No reassignment.
    """

    def __init__(self):
        self.active_incidents: dict[str, Incident] = {}
        self.incident_queue: list[dict] = []

    def on_new_marker(self, marker: dict) -> str:
        """Register a new marker.

        Returns 'created' if this is the first incident,
        or 'queued' if there's already an active incident.
        """
        if not self.active_incidents:
            self.create_incident(marker)
            return "created"
        else:
            self.queue_incident(marker)
            return "queued"

    def create_incident(self, marker: dict) -> Incident:
        """Create a new active incident from a marker."""
        incident = Incident(marker=marker)
        incident.status = "active"
        marker_id = marker.get("id", "unknown")
        self.active_incidents[marker_id] = incident
        logger.info("incident_created", marker_id=marker_id, type=marker.get("type"))
        return incident

    def queue_incident(self, marker: dict) -> None:
        """Add marker to the pending queue."""
        self.incident_queue.append(marker)
        marker_id = marker.get("id", "unknown")
        logger.info("incident_queued", marker_id=marker_id, queue_depth=len(self.incident_queue))

    def complete_incident(self, marker_id: str) -> None:
        """Mark incident resolved and promote next queued if present."""
        if marker_id in self.active_incidents:
            del self.active_incidents[marker_id]
            logger.info("incident_completed", marker_id=marker_id)

        if self.incident_queue:
            next_marker = self.incident_queue.pop(0)
            self.create_incident(next_marker)
            logger.info("incident_promoted", marker_id=next_marker.get("id"))

    def get_active(self) -> dict[str, Incident]:
        """Return all active incidents."""
        return self.active_incidents

    def get_queue_depth(self) -> int:
        """Return number of queued incidents."""
        return len(self.incident_queue)
