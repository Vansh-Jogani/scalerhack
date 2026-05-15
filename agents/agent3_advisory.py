"""Agent 3 — Advisory Agent (Claude API).

Event-driven — NOT a loop. Does NOT inherit BaseAgent.
Produces structured advisory for human first responders.

System prompt is EXACTLY from SPEC.md AGENT_3_SYSTEM_PROMPT.
Output format: 6 named sections in plain text.

Triggers per SPEC.md AGENT_3_CONFIG:
  - agent_1_report_received
  - agent_2_findings_updated
  - world_event_fired
  - operator_query
  - 60s_heartbeat_check
"""

import asyncio
from datetime import datetime, timezone

import structlog
from anthropic import AsyncAnthropic

from sim_layer.tracer import tracer

logger = structlog.get_logger()

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
    Uses Claude API for reasoning.
    """

    def __init__(
        self,
        agent_id: str,
        model: str = "claude-sonnet-4-20250514",
        orchestrator=None,
        stream_callback=None,
    ):
        self.agent_id = agent_id
        self.model = model
        self.orchestrator = orchestrator
        self.stream_callback = stream_callback
        self.client = AsyncAnthropic()
        self.latest_advisory: dict | None = None

        # Debounce state for agent_2_findings_updated
        self._debounce_task: asyncio.Task | None = None
        self._debounce_pending: dict | None = None

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

    async def _debounced_trigger(
        self, agent1_report: dict, agent2_report: dict, extra_context: dict | None
    ) -> dict:
        """15-second debounce for agent_2_findings_updated.

        Multiple rapid world state writes batch into one invocation.
        """
        self._debounce_pending = {
            "agent1_report": agent1_report,
            "agent2_report": agent2_report,
            "extra_context": extra_context,
        }

        if self._debounce_task and not self._debounce_task.done():
            # Already waiting — the pending data will be used when the timer fires
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
        # Return current advisory immediately; the debounced one will emit via callback
        return self.latest_advisory or {"text": "Advisory update pending (debounced)..."}

    async def _execute(
        self,
        trigger_type: str,
        agent1_report: dict,
        agent2_report: dict,
        extra_context: dict | None = None,
    ) -> dict:
        """Execute advisory generation via Claude API."""
        with tracer.start_span("agent3.advisory", trigger=trigger_type):
            prompt = self._build_prompt(trigger_type, agent1_report, agent2_report, extra_context)

            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=AGENT_3_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )

                text = self._extract_text(response)

                # Validate all 6 sections present
                if not self._validate_sections(text):
                    logger.warning("advisory_missing_sections", trigger=trigger_type)
                    # Retry once with stricter prompt
                    retry_prompt = (
                        prompt + "\n\nYou MUST include all six sections. "
                        "Missing sections will cause system failure."
                    )
                    response = await self.client.messages.create(
                        model=self.model,
                        max_tokens=2048,
                        system=AGENT_3_SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": retry_prompt}],
                    )
                    text = self._extract_text(response)

                    if not self._validate_sections(text):
                        logger.error("advisory_retry_failed", trigger=trigger_type)
                        text = self._error_advisory(agent1_report, agent2_report)

                advisory = {
                    "text": text,
                    "trigger": trigger_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sections": self._parse_sections(text),
                }

                self.latest_advisory = advisory
                logger.info("advisory_issued", trigger=trigger_type)

                # Emit via callback if available
                if self.stream_callback:
                    await self.stream_callback("advisory", advisory)

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

    def _build_prompt(
        self,
        trigger_type: str,
        agent1_report: dict,
        agent2_report: dict,
        extra_context: dict | None,
    ) -> str:
        """Build the user prompt from available reports."""
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
        """Check that all 6 required sections are present."""
        upper = text.upper()
        return all(section in upper for section in REQUIRED_SECTIONS)

    def _parse_sections(self, text: str) -> dict:
        """Parse the 6 sections from advisory text into a dict."""
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
                    # Get content after the colon on the same line
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
        """Produce a structured error advisory — never crashes."""
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

    def _extract_text(self, response) -> str:
        """Extract text from Claude response."""
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)
