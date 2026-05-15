"""Agent 3 — Advisory Agent (Claude API with tool use).

Receives an IncidentBriefing from the orchestrator event bus.
Produces a structured advisory by calling the issue_advisory tool —
Claude is forced to call the tool, so the output schema is always valid.

Event-driven, not a loop. Triggered by the EventBus.
"""

from datetime import datetime, timezone
import structlog
from anthropic import AsyncAnthropic

from prompts import load_prompt
from agents.tools.schemas import AGENT_3_TOOLS, IssueAdvisoryInput
from agents.messages import IncidentBriefing

logger = structlog.get_logger()


class AdvisoryAgent:
    """Agent 3: produces structured advisory from IncidentBriefing via Claude API."""

    def __init__(self, agent_id: str, model: str, orchestrator):
        self.agent_id = agent_id
        self.model = model
        self.orchestrator = orchestrator
        self.client = AsyncAnthropic()
        self.latest_advisory: dict | None = None
        self._prompt = load_prompt("agent3_advisory")

    async def on_trigger(self, incident_briefing: IncidentBriefing) -> dict:
        """Called by EventBus when a trigger fires. Produces advisory via tool use."""
        briefing_json = incident_briefing.model_dump_json(indent=2)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Generate an advisory based on this incident briefing:\n\n"
                    f"{briefing_json}"
                ),
            }
        ]

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self._prompt["text"],
                messages=messages,
                tools=AGENT_3_TOOLS,
                tool_choice={"type": "tool", "name": "issue_advisory"},
            )

            tool_block = next(
                (b for b in response.content if b.type == "tool_use" and b.name == "issue_advisory"),
                None,
            )

            if tool_block is None:
                logger.warning("agent3_no_tool_call", stop_reason=response.stop_reason)
                return self._fallback_advisory(incident_briefing)

            _, err = IssueAdvisoryInput.validate_call(tool_block.input)
            if err:
                logger.error("agent3_invalid_advisory_schema", error=err)
                return self._fallback_advisory(incident_briefing)

            advisory = dict(tool_block.input)
            advisory["last_updated"] = datetime.now(timezone.utc).isoformat()
            advisory["based_on"] = {
                "incident_id": incident_briefing.incident_id,
                "coverage_pct": (
                    incident_briefing.swarm_findings.coverage_pct
                    if incident_briefing.swarm_findings else 0.0
                ),
            }
            advisory["prompt_version"] = self._prompt["version_hash"]

            self.latest_advisory = advisory
            logger.info(
                "advisory_issued",
                incident_id=incident_briefing.incident_id,
                trigger=incident_briefing.trigger_type,
                prompt_version=self._prompt["version_hash"],
            )
            return advisory

        except Exception as exc:
            logger.error("agent3_error", error=str(exc))
            return self._fallback_advisory(incident_briefing)

    def _fallback_advisory(self, incident_briefing: IncidentBriefing) -> dict:
        """Produce minimal advisory without LLM — used only on API failure."""
        report = incident_briefing.surveillance_report
        hazards = report.sensor_summary.hazard_flags
        advisory = {
            "situation_summary": (
                f"Incident {report.classification} detected with "
                f"{report.confidence:.0%} confidence. Automated advisory — LLM unavailable."
            ),
            "immediate_actions": [
                "1. Establish perimeter at confirmed exclusion radius",
                "2. Deploy ground teams to safe approach routes only",
            ],
            "exclusion_zones": [],
            "resource_requirements": ["Incident commander", "Hazmat team on standby"],
            "risk_flags": (
                [f"Detected hazards: {', '.join(hazards)}"] if hazards
                else ["No hazards confirmed — treat as unknown"]
            ),
            "monitoring_status": "Drone surveillance active. Advisory will update on next trigger.",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "based_on": {
                "incident_id": incident_briefing.incident_id,
                "coverage_pct": (
                    incident_briefing.swarm_findings.coverage_pct
                    if incident_briefing.swarm_findings else 0.0
                ),
            },
        }
        self.latest_advisory = advisory
        return advisory
