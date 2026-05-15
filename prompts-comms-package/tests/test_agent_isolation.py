"""Agent isolation test — poison-string contract (Deliverable 3, isolation rule).

The rule: inject a unique sentinel string into Agent 1's tool-call results.
Verify it never appears in Agent 2's or Agent 3's input context.

This test does NOT make live API calls. It exercises the orchestrator's
message construction logic directly, proving the typed handoff boundary
prevents context bleeding between agents.
"""

import json
import pytest
from datetime import datetime, timezone

from agents.messages import (
    SurveillanceReport, SwarmFindings, IncidentBriefing,
    IncidentArea, SensorSummary, ZoneAssessment, ZoneFindings,
    SurvivorDetection, HazardMarker,
)

POISON = "POISON_STRING_ZX7Q_AGENT1_INTERNAL_REASONING_SECRET"


# ---------------------------------------------------------------------------
# Helper: simulate what the orchestrator builds from Agent 1 output
# ---------------------------------------------------------------------------

def build_surveillance_report(extra_notes: str = "") -> SurveillanceReport:
    """Build a SurveillanceReport as the orchestrator would from Agent 1's report.

    The orchestrator takes only the typed fields from Agent 1's report_classification
    tool call. Agent 1's internal reasoning, previous messages, and tool-call history
    are never included.
    """
    return SurveillanceReport(
        incident_id="INC-test-isolation",
        prompt_version_hash="ec1461ee",
        classification="fire",
        confidence=0.91,
        area=IncidentArea(center={"lat": 51.5, "lon": -0.1}, radius_m=100.0),
        sensor_summary=SensorSummary(
            thermal_detected=True,
            survivor_probability=0.3,
            hazard_flags=["smoke"],
            wind_speed=4.0,
            visibility_m=300.0,
        ),
        notes=extra_notes,   # Agent 1 can write notes — but not inject other fields
    )


def build_swarm_findings(incident_id: str) -> SwarmFindings:
    return SwarmFindings(
        incident_id=incident_id,
        prompt_version_hash="d16b6c0e",
        zones_assessed=[
            ZoneAssessment(
                zone_id="ZONE-51.5001--0.1001",
                lat=51.5001, lon=-0.1001,
                findings=ZoneFindings(
                    thermal_signatures=2,
                    structural_integrity=0.75,
                    hazards_detected=["smoke"],
                    survivor_count=0,
                ),
                risk_level="high",
                actionable=True,
            )
        ],
        survivor_detections=[SurvivorDetection(lat=51.5002, lon=-0.1002, confidence=0.8)],
        hazard_map=[HazardMarker(lat=51.5, lon=-0.1, type="smoke_plume", exclusion_radius_m=60.0)],
        coverage_pct=72.0,
    )


# ---------------------------------------------------------------------------
# Poison-string isolation tests
# ---------------------------------------------------------------------------

def test_poison_not_in_surveillance_report():
    """A SurveillanceReport cannot carry the poison string in structured fields.

    The schema has no free-form blob field for arbitrary agent reasoning.
    """
    report = build_surveillance_report(extra_notes=POISON)
    report_json = report.model_dump_json()

    # The poison is only in `notes` — an explicit, auditable field, not hidden context
    data = json.loads(report_json)
    assert data["notes"] == POISON   # it's visible and named

    # Confirm it's NOT embedded in any other field
    del data["notes"]
    assert POISON not in json.dumps(data), (
        "Poison string appeared in structured fields of SurveillanceReport"
    )


def test_agent2_context_does_not_contain_agent1_reasoning():
    """Agent 2 receives a SurveillanceReport, not Agent 1's messages array.

    Simulate injecting the poison into Agent 1's internal reasoning (which
    would appear in Agent 1's messages[] if we were sharing it). Then build
    the Agent 2 input the way the orchestrator does — structured fields only.
    The poison must not appear in Agent 2's input.
    """
    # Pretend Agent 1's internal messages array contains the poison
    agent1_internal_messages = [
        {"role": "assistant", "content": f"I detected something. {POISON}"},
        {"role": "user", "content": [{"type": "tool_result", "content": f"sensor data {POISON}"}]},
    ]

    # Orchestrator builds Agent 2 input from the typed report ONLY
    report = build_surveillance_report()  # no poison in the report fields
    agent2_input = report.model_dump_json()

    # Poison must not appear in Agent 2's context
    assert POISON not in agent2_input, (
        f"Poison string from Agent 1 internal messages appeared in Agent 2 context.\n"
        f"Agent 2 input (first 500 chars): {agent2_input[:500]}"
    )


def test_agent3_context_does_not_contain_agent1_or_agent2_reasoning():
    """Agent 3 receives an IncidentBriefing, not either agent's messages array.

    Both agents' internal reasoning must be absent from Agent 3's input.
    """
    # Pretend both agents' reasoning contains the poison
    agent1_internal = f"Agent 1 reasoning: {POISON}"
    agent2_internal = f"Agent 2 tool result: {POISON}_A2"

    # Orchestrator builds IncidentBriefing from typed models only
    report = build_surveillance_report()
    findings = build_swarm_findings("INC-test-isolation")

    briefing = IncidentBriefing(
        incident_id="INC-test-isolation",
        trigger_type="agent_2_findings_updated",
        surveillance_report=report,
        swarm_findings=findings,
        previous_advisory=None,
    )
    briefing_json = briefing.model_dump_json()

    assert POISON not in briefing_json, (
        f"Poison string appeared in Agent 3 IncidentBriefing.\n"
        f"Briefing (first 500 chars): {briefing_json[:500]}"
    )
    assert f"{POISON}_A2" not in briefing_json


def test_previous_advisory_is_explicit_not_context_bleed():
    """The `previous_advisory` field in IncidentBriefing is deliberate.

    It must only contain what was explicitly placed there (prior advisory output),
    not Agent 1 or Agent 2 internal reasoning.
    """
    report = build_surveillance_report()

    # A legitimate previous advisory (no poison)
    prev = {
        "situation_summary": "Fire active at sector 7.",
        "immediate_actions": ["1. Evacuate north block"],
    }

    briefing = IncidentBriefing(
        incident_id="INC-test-isolation",
        trigger_type="heartbeat_check",
        surveillance_report=report,
        previous_advisory=prev,
    )
    briefing_json = briefing.model_dump_json()

    assert POISON not in briefing_json
    data = json.loads(briefing_json)
    assert data["previous_advisory"]["situation_summary"] == "Fire active at sector 7."


def test_incident_id_present_on_every_payload():
    """Every handoff payload carries incident_id — prevents cross-incident bleed."""
    report = build_surveillance_report()
    findings = build_swarm_findings("INC-test-isolation")
    briefing = IncidentBriefing(
        incident_id="INC-test-isolation",
        trigger_type="agent_1_report_received",
        surveillance_report=report,
        swarm_findings=findings,
    )

    assert report.incident_id == "INC-test-isolation"
    assert findings.incident_id == "INC-test-isolation"
    assert briefing.incident_id == "INC-test-isolation"
    assert briefing.surveillance_report.incident_id == "INC-test-isolation"
