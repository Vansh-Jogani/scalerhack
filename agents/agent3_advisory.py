"""Agent 3 — Advisory Agent (Claude API, tool-use enforced).

Event-driven, not a loop. Receives IncidentBriefing, issues structured advisory
via the issue_advisory tool. No Ollama dependency.
"""

from datetime import datetime, timezone
import structlog
from anthropic import AsyncAnthropic

from agents.tools.report_tools import ISSUE_ADVISORY_TOOL
from prompts.registry import load_prompt

logger = structlog.get_logger()


class AdvisoryAgent:
    """Agent 3: produces structured advisory from IncidentBriefing via Claude API."""

    def __init__(self, model: str, orchestrator) -> None:
        self.model = model
        self.orchestrator = orchestrator
        self.client = AsyncAnthropic()
        self.latest_advisory: dict | None = None

        prompt_data = load_prompt("agent3_advisory")
        self._system_prompt = prompt_data["text"]

    async def on_trigger(self, briefing) -> dict:
        """Produce advisory from IncidentBriefing. Returns advisory dict."""
        briefing_dict = (
            briefing.to_context_dict()
            if hasattr(briefing, "to_context_dict")
            else briefing
        )

        messages = [
            {
                "role": "user",
                "content": f"Issue an advisory based on these incident reports:\n{briefing_dict}",
            }
        ]

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._system_prompt,
                messages=messages,
                tools=[ISSUE_ADVISORY_TOOL],
                tool_choice={"type": "tool", "name": "issue_advisory"},
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "issue_advisory":
                    advisory = dict(block.input)
                    advisory["last_updated"] = datetime.now(timezone.utc).isoformat()
                    self.latest_advisory = advisory
                    logger.info("advisory_issued", incident_id=briefing_dict.get("incident_id"))
                    try:
                        from comms.twilio_client import send_advisory_broadcast
                        immediate_actions = advisory.get("immediate_actions", [])
                        immediate = immediate_actions[0] if immediate_actions else "Evacuate the affected area immediately."
                        send_advisory_broadcast(
                            disaster_type=briefing_dict.get("disaster_type", briefing_dict.get("classification", "unknown")),
                            severity=briefing_dict.get("severity", "high"),
                            location_name="Kondapur, Hyderabad",
                            immediate_action=immediate,
                            incident_id=briefing_dict.get("incident_id", "UNKNOWN"),
                        )
                    except Exception as _adv_err:
                        logger.warning("advisory_broadcast_failed", error=str(_adv_err))
                    return advisory

        except Exception as e:
            logger.error("agent3_error", error=str(e))

        return self._fallback_advisory(briefing_dict)

    def _fallback_advisory(self, briefing_dict: dict) -> dict:
        sr = briefing_dict.get("surveillance_report") or {}
        sf = briefing_dict.get("swarm_findings") or {}
        advisory = {
            "situation_summary": (
                f"Incident {sr.get('classification', 'unknown')} detected at confidence "
                f"{sr.get('confidence', 0)}. Specialist swarm coverage at {sf.get('coverage_pct', 0)}%."
            ),
            "immediate_actions": [
                "1. Establish perimeter at exclusion radius",
                "2. Deploy ground teams to safe approach routes",
                "3. Confirm command structure and communications",
            ],
            "exclusion_zones": [],
            "resource_requirements": ["Incident commander", "Hazmat team on standby"],
            "risk_flags": [f"Hazards: {sr.get('sensor_summary', {}).get('hazard_flags', [])}"],
            "monitoring_status": f"Coverage at {sf.get('coverage_pct', 0)}%, drone monitoring active",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "based_on": {
                "incident_id": briefing_dict.get("incident_id", ""),
                "coverage_pct": sf.get("coverage_pct", 0.0),
            },
        }
        self.latest_advisory = advisory
        return advisory
