"""Agent 3 — Advisory Agent (Claude API, claude-sonnet-4-20250514).

Event-driven — NOT a loop. Does NOT inherit BaseAgent.
Produces structured advisory for human first responders.

System prompt is EXACTLY from SPEC.md AGENT_3_SYSTEM_PROMPT.
Output format: 6 named sections in plain text.

Uses the Anthropic API (ANTHROPIC_API_KEY from env). Model is injected by
the orchestrator (claude-sonnet-4-20250514). No Ollama dependency.

Triggers per SPEC.md AGENT_3_CONFIG:
  - agent_1_report_received
  - agent_2_findings_updated
  - world_event_fired
  - operator_query
  - 60s_heartbeat_check
"""

import asyncio
from datetime import datetime, timezone

import anthropic
import structlog

from sim_layer.tracer import tracer

logger = structlog.get_logger()

DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Module-level tracker: ensures only one debounce task runs across all instances.
# New instances cancel stale tasks from previous instances.
_active_debounce_task: asyncio.Task | None = None

# Verbatim from SPEC.md — do not modify
AGENT_3_SYSTEM_PROMPT = """You are ARIA Advisory Agent. You issue response plans for human first responders.

You receive: Full reports from surveillance and specialist swarm agents
You produce: Clear, actionable response plans

Your output format is always:
SITUATION SUMMARY: [2-3 sentences, what is happening]
IMMEDIATE ACTIONS (next 15 min): [numbered list]
EXCLUSION ZONES: [areas humans must not enter, with reasons]
RESOURCE REQUIREMENTS: [personnel, equipment needed]
RISK FLAGS: [what could get worse and why]
MONITORING: [what agents are watching, update frequency]

You update your advisory when:
- New agent data arrives
- Disaster area grows
- New survivors detected
- Hazard conditions change

You are direct. First responders need clarity, not caveats.
"""

REQUIRED_SECTIONS = [
    "SITUATION SUMMARY",
    "IMMEDIATE ACTIONS",
    "EXCLUSION ZONES",
    "RESOURCE REQUIREMENTS",
    "RISK FLAGS",
    "MONITORING",
]


class AdvisoryAgent:
    """Agent 3: Advisory — produces response plans for first responders.

    Event-driven, NOT a loop. Triggered by orchestrator on specific events.
    Uses the Anthropic API (claude-sonnet-4-20250514). No Ollama dependency.
    """

    def __init__(
        self,
        agent_id: str,
        model: str = DEFAULT_MODEL,
        orchestrator=None,
        stream_callback=None,
    ):
        self.agent_id = agent_id
        self.model = model
        self.orchestrator = orchestrator
        self.stream_callback = stream_callback
        self.latest_advisory: dict | None = None

        # Debounce state for agent_2_findings_updated
        self._debounce_task: asyncio.Task | None = None
        self._debounce_pending: dict | None = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def on_trigger(
        self,
        trigger_type: str,
        agent1_report: dict,
        agent2_report: dict,
        extra_context: dict | None = None,
    ) -> dict:
        """Main entry point — called when a trigger fires.

        Applies 15-second debounce on agent_2_findings_updated.
        All other triggers execute immediately.
        """
        if trigger_type == "agent_2_findings_updated":
            return await self._debounced_trigger(agent1_report, agent2_report, extra_context)

        return await self._execute(trigger_type, agent1_report, agent2_report, extra_context)

    # ------------------------------------------------------------------
    # Debounce
    # ------------------------------------------------------------------

    async def _debounced_trigger(
        self, agent1_report: dict, agent2_report: dict, extra_context: dict | None
    ) -> dict:
        """15-second debounce for agent_2_findings_updated."""
        global _active_debounce_task

        self._debounce_pending = {
            "agent1_report": agent1_report,
            "agent2_report": agent2_report,
            "extra_context": extra_context,
        }

        # Cancel any stale task from a previous AdvisoryAgent instance
        if _active_debounce_task and not _active_debounce_task.done():
            logger.info("advisory_debounce_merged", trigger="agent_2_findings_updated")
            return self.latest_advisory or {"text": "Advisory update pending (debounced)..."}

        async def _fire_after_delay():
            await asyncio.sleep(15)
            if self._debounce_pending:
                p = self._debounce_pending
                self._debounce_pending = None
                await self._execute(
                    "agent_2_findings_updated",
                    p["agent1_report"],
                    p["agent2_report"],
                    p["extra_context"],
                )

        self._debounce_task = asyncio.create_task(_fire_after_delay())
        _active_debounce_task = self._debounce_task
        return self.latest_advisory or {"text": "Advisory update pending (debounced)..."}

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        trigger_type: str,
        agent1_report: dict,
        agent2_report: dict,
        extra_context: dict | None = None,
    ) -> dict:
        """Execute advisory generation via the Anthropic API."""
        # Emit started event
        await self._emit("started", {"trigger_type": trigger_type})

        with tracer.start_span("agent3.advisory", trigger=trigger_type):
            prompt = self._build_prompt(trigger_type, agent1_report, agent2_report, extra_context)

            try:
                text = await self._call_claude(prompt)

                # Validate all 6 sections present
                if not self._validate_sections(text):
                    logger.warning("advisory_missing_sections", trigger=trigger_type)
                    # Retry once with stricter prompt
                    retry_prompt = (
                        prompt + "\n\nYou MUST include all six sections. "
                        "Missing sections will cause system failure."
                    )
                    text = await self._call_claude(retry_prompt)

                    if not self._validate_sections(text):
                        logger.error("advisory_retry_failed", trigger=trigger_type)
                        text = self._error_advisory(agent1_report, agent2_report)

                sections = self._parse_sections(text)
                advisory = {
                    "text": text,
                    "trigger": trigger_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sections": sections,
                }

                self.latest_advisory = advisory
                logger.info("advisory_issued", trigger=trigger_type)

                # Emit completed event (orchestrator handles the advisory broadcast)
                await self._emit("completed", {
                    "trigger": trigger_type,
                    "sections": list(sections.keys()),
                })

                return advisory

            except Exception as e:
                logger.error("agent3_error", error=str(e), trigger=trigger_type)
                error_text = self._error_advisory(agent1_report, agent2_report)
                advisory = {
                    "text": error_text,
                    "trigger": trigger_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
                self.latest_advisory = advisory
                return advisory

    # ------------------------------------------------------------------
    # Anthropic API client
    # ------------------------------------------------------------------

    async def _call_claude(self, prompt: str) -> str:
        """Call the Anthropic API and return the response text."""
        client = anthropic.AsyncAnthropic()
        message = await client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=AGENT_3_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        trigger_type: str,
        agent1_report: dict,
        agent2_report: dict,
        extra_context: dict | None,
    ) -> str:
        parts = [f"Trigger: {trigger_type}\n"]
        if agent1_report:
            parts.append(f"SURVEILLANCE REPORT (Agent 1):\n{agent1_report}\n")
        if agent2_report:
            parts.append(f"SPECIALIST SWARM FINDINGS (Agent 2):\n{agent2_report}\n")
        if extra_context:
            parts.append(f"ADDITIONAL CONTEXT:\n{extra_context}\n")
        parts.append(
            "Based on the above, produce your advisory now. "
            "Include all six sections in the specified format."
        )
        return "\n".join(parts)

    def _validate_sections(self, text: str) -> bool:
        upper = text.upper()
        return all(section in upper for section in REQUIRED_SECTIONS)

    def _parse_sections(self, text: str) -> dict:
        sections = {}
        current_section = None
        current_lines = []

        for line in text.split("\n"):
            line_upper = line.strip().upper()
            matched = False
            for section in REQUIRED_SECTIONS:
                if line_upper.startswith(section):
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = section.lower().replace(" ", "_")
                    colon_idx = line.find(":")
                    if colon_idx >= 0:
                        remainder = line[colon_idx + 1:].strip()
                        current_lines = [remainder] if remainder else []
                    else:
                        current_lines = []
                    matched = True
                    break
            if not matched and current_section:
                current_lines.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()

        return sections

    def _error_advisory(self, agent1_report: dict, agent2_report: dict) -> str:
        classification = agent1_report.get("classification", "unknown")
        confidence = agent1_report.get("confidence", 0)
        return (
            f"SITUATION SUMMARY: {classification} incident detected with "
            f"confidence {confidence}. Advisory generation encountered an error. "
            f"Manual assessment recommended.\n"
            f"IMMEDIATE ACTIONS (next 15 min):\n"
            f"1. Establish perimeter at safe distance\n"
            f"2. Deploy ground teams to assess situation\n"
            f"3. Await updated advisory\n"
            f"EXCLUSION ZONES: Pending assessment — maintain 200m standoff\n"
            f"RESOURCE REQUIREMENTS: Incident commander, hazmat team on standby\n"
            f"RISK FLAGS: Advisory system error — manual assessment required\n"
            f"MONITORING: Drone surveillance active, update frequency: manual"
        )

    async def _emit(self, event: str, content) -> None:
        """Emit agent_stream event via stream_callback."""
        if self.stream_callback:
            try:
                await self.stream_callback("agent_stream", {
                    "agent_id": self.agent_id,
                    "event": event,
                    "content": content,
                })
            except Exception as e:
                logger.warning("agent3_emit_error", event=event, error=str(e))
