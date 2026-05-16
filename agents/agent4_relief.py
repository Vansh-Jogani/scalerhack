"""Agent 4 — Relief Helper Agent.

Pre-fetches nearest response centres for the incident's disaster type,
then calls the LLM once (tool_choice=issue_relief_plan) to produce a
structured ground-level relief dispatch plan.
"""

import structlog
from anthropic import AsyncAnthropic

from agents.tools.relief_tools import (
    FIND_NEAREST_CENTRE_TOOL,
    ISSUE_RELIEF_PLAN_TOOL,
    create_find_nearest_centre_handler,
    create_issue_relief_plan_handler,
)
from prompts.registry import load_prompt

logger = structlog.get_logger()

# Response centre types to query per disaster classification
CENTRE_PRIORITY_MAP: dict[str, list[str]] = {
    "fire":                ["FIRE_STATION", "HOSPITAL", "NDRF"],
    "structural_collapse": ["NDRF", "CIVIL_DEFENCE", "HOSPITAL"],
    "flood":               ["NDRF", "SDRF", "MUNICIPAL_EMERGENCY", "HOSPITAL"],
    "industrial_hazard":   ["FIRE_STATION", "NDRF", "HOSPITAL"],
    "maritime_sar":        ["AIRPORT_EMERGENCY", "NDRF", "HOSPITAL"],
}


class ReliefAgent:
    """Agent 4: locates nearest rescue units, issues structured relief plan."""

    def __init__(
        self,
        agent_id: str,
        model: str,
        orchestrator,
        response_centres: list,
        stream_callback=None,
    ):
        self.agent_id = agent_id
        self.model = model
        self.orchestrator = orchestrator
        self.stream_callback = stream_callback
        self.client = AsyncAnthropic()

        prompt_data = load_prompt("agent4_relief")
        self._system_prompt = prompt_data["text"]

        self._tool_handlers = {
            "find_nearest_centre": create_find_nearest_centre_handler(response_centres),
            "issue_relief_plan":   create_issue_relief_plan_handler(orchestrator),
        }

    async def _emit(self, event: str, content) -> None:
        if self.stream_callback:
            await self.stream_callback(
                "agent_stream",
                {"agent_id": self.agent_id, "event": event, "content": content},
            )

    async def run(self, advisory: dict, incident_context: dict) -> None:
        classification = incident_context.get("classification", "unknown")
        area = incident_context.get("area", {})
        center = area.get("center", {})
        incident_lat = center.get("lat", 17.3880)
        incident_lon = center.get("lon", 78.4895)
        incident_id = incident_context.get("incident_id", "")

        relevant_types = CENTRE_PRIORITY_MAP.get(classification, ["NDRF", "HOSPITAL", "FIRE_STATION"])

        await self._emit(
            "relief_started",
            f"Locating rescue units for {classification.upper()} — querying {len(relevant_types)} unit types",
        )

        # Pre-fetch nearest centres for each relevant type
        nearest_centres: dict[str, list] = {}
        for ctype in relevant_types:
            result = await self._tool_handlers["find_nearest_centre"](
                centre_type=ctype,
                incident_lat=incident_lat,
                incident_lon=incident_lon,
                limit=3,
            )
            if result.get("status") == "ok" and result["centres"]:
                nearest_centres[ctype] = result["centres"]
                names = ", ".join(c["name"] for c in result["centres"][:2])
                dists = ", ".join(f"{c['distance_m']}m" for c in result["centres"][:2])
                await self._emit("centre_found", f"{ctype} — {names} ({dists})")
            else:
                await self._emit("centre_missing", f"No {ctype} units found — will flag as resource gap")

        observations = {
            "incident_id": incident_id,
            "classification": classification,
            "incident_location": {"lat": incident_lat, "lon": incident_lon},
            "advisory_summary": advisory.get("situation_summary", ""),
            "immediate_actions": advisory.get("immediate_actions", []),
            "exclusion_zones": advisory.get("exclusion_zones", []),
            "risk_flags": advisory.get("risk_flags", []),
            "available_response_centres": nearest_centres,
        }

        total_units = sum(len(v) for v in nearest_centres.values())
        await self._emit(
            "llm_call",
            f"Calling {self.model} · tool_choice=issue_relief_plan · {total_units} candidate units across {len(nearest_centres)} types",
        )

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self._system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"Coordinate immediate relief response:\n{observations}",
                    }
                ],
                tools=[FIND_NEAREST_CENTRE_TOOL, ISSUE_RELIEF_PLAN_TOOL],
                tool_choice={"type": "tool", "name": "issue_relief_plan"},
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "issue_relief_plan":
                    result = await self._tool_handlers["issue_relief_plan"](**block.input)
                    units = len(block.input.get("dispatched_units", []))
                    triage = len(block.input.get("triage_sites", []))
                    note = block.input.get("coordination_note", "")
                    await self._emit(
                        "relief_issued",
                        f"Relief plan filed — {units} units dispatched · {triage} triage sites · {note[:100]}",
                    )
                    logger.info("agent4_relief_issued", incident_id=incident_id, units=units)
                    return

        except Exception as e:
            logger.error("agent4_error", error=str(e))
            await self._emit("error", {"message": str(e)})
            # Resolve future with a fallback plan so the pipeline doesn't hang
            self.orchestrator.receive_agent4_plan(
                self._fallback_plan(incident_id, nearest_centres)
            )

    def _fallback_plan(self, incident_id: str, nearest_centres: dict) -> dict:
        dispatched = []
        for ctype, centres in nearest_centres.items():
            for c in centres[:1]:
                dispatched.append({**c, "role": f"Immediate {ctype.replace('_', ' ').lower()} response"})
        return {
            "incident_id": incident_id,
            "dispatched_units": dispatched,
            "triage_sites": [],
            "evacuation_routes": [{"description": "Move upwind from incident", "direction": "north", "notes": "Pending full assessment"}],
            "resource_gaps": [],
            "coordination_note": "Fallback plan — LLM unavailable. Nearest units pre-dispatched.",
        }
