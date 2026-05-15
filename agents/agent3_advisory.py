"""Agent 3 — Advisory Agent (Local Ollama).

Receives combined Agent 1 + Agent 2 reports. Produces structured advisory
for human first responders. Event-driven, not a loop.
"""

import asyncio
from datetime import datetime, timezone

import structlog
import httpx

logger = structlog.get_logger()

AGENT_3_SYSTEM_PROMPT = """You are ARIA Advisory Agent. You issue response plans for human first responders.

You receive: Full reports from surveillance and specialist swarm agents.
You produce: Clear, actionable response plans as structured JSON.

Your output MUST be valid JSON with exactly these fields:
{
  "situation_summary": "2-3 sentences describing what is happening",
  "immediate_actions": ["numbered action items, max 5"],
  "exclusion_zones": [{"lat": 0.0, "lon": 0.0, "radius_m": 0.0, "reason": ""}],
  "resource_requirements": ["personnel and equipment needed"],
  "risk_flags": ["what could get worse and why"],
  "monitoring_status": "what agents are watching, update frequency",
  "last_updated": "ISO timestamp",
  "based_on": {"incident_id": "", "coverage_pct": 0.0}
}

Rules:
- immediate_actions: max 5 items, numbered
- You are direct. First responders need clarity, not caveats.
- Update when new data arrives, disaster grows, or conditions change.
"""

ISSUE_ADVISORY_TOOL = {
    "name": "issue_advisory",
    "description": "Issue a structured advisory for first responders based on combined agent reports.",
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
            "last_updated": {"type": "string", "description": "ISO timestamp"},
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


class AdvisoryAgent:
    """Agent 3: produces advisory from combined Agent 1 + Agent 2 reports via local Ollama."""

    def __init__(self, agent_id: str, endpoint: str, model: str, orchestrator):
        self.agent_id = agent_id
        self.endpoint = endpoint
        self.model = model
        self.orchestrator = orchestrator
        self.latest_advisory = None

    async def on_trigger(self, agent1_report: dict, agent2_report: dict) -> dict:
        """Called when new data arrives. Produces advisory from both reports."""
        combined_input = {
            "agent1_report": agent1_report,
            "agent2_report": agent2_report,
        }

        prompt = f"Generate an advisory based on these reports:\n\n{combined_input}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": AGENT_3_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "format": "json",
                    },
                )
                response.raise_for_status()
                result = response.json()
                content = result.get("message", {}).get("content", "{}")

                import json
                advisory = json.loads(content)
                advisory["last_updated"] = datetime.now(timezone.utc).isoformat()
                advisory["based_on"] = {
                    "incident_id": agent1_report.get("incident_id", ""),
                    "coverage_pct": agent2_report.get("coverage_pct", 0.0),
                }

                self.latest_advisory = advisory
                logger.info("advisory_issued", incident_id=advisory["based_on"]["incident_id"])
                return advisory

        except Exception as e:
            logger.error("agent3_error", error=str(e))
            return self._fallback_advisory(agent1_report, agent2_report)

    def _fallback_advisory(self, agent1_report: dict, agent2_report: dict) -> dict:
        """Produce structured advisory without LLM (fallback)."""
        advisory = {
            "situation_summary": f"Incident {agent1_report.get('classification', 'unknown')} detected with confidence {agent1_report.get('confidence', 0)}.",
            "immediate_actions": ["Establish perimeter at exclusion radius", "Deploy ground teams to safe approach routes"],
            "exclusion_zones": [],
            "resource_requirements": ["Incident commander", "Hazmat team on standby"],
            "risk_flags": [f"Hazards: {', '.join(agent1_report.get('sensor_summary', {}).get('hazard_flags', []))}"],
            "monitoring_status": f"Coverage at {agent2_report.get('coverage_pct', 0)}%, monitoring active",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "based_on": {
                "incident_id": agent1_report.get("incident_id", ""),
                "coverage_pct": agent2_report.get("coverage_pct", 0.0),
            },
        }
        self.latest_advisory = advisory
        return advisory
