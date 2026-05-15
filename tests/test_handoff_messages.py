"""Tests for handoff message schemas (Deliverable 3)."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agents.messages import (
    SurveillanceReport, SwarmFindings, IncidentBriefing, WorldEvent,
    ZoneAssessment, ZoneFindings, SurvivorDetection, HazardMarker,
    IncidentArea, SensorSummary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sensor_summary():
    return SensorSummary(
        thermal_detected=True,
        survivor_probability=0.4,
        hazard_flags=["smoke", "high_temp"],
        wind_speed=5.2,
        visibility_m=200.0,
    )


@pytest.fixture
def surveillance_report(sensor_summary):
    return SurveillanceReport(
        incident_id="INC-1000000000",
        prompt_version_hash="ec1461ee",
        classification="fire",
        confidence=0.92,
        area=IncidentArea(center={"lat": 51.5, "lon": -0.1}, radius_m=100.0),
        sensor_summary=sensor_summary,
        notes="Smoke visible on western edge",
    )


@pytest.fixture
def swarm_findings():
    return SwarmFindings(
        incident_id="INC-1000000000",
        prompt_version_hash="d16b6c0e",
        zones_assessed=[
            ZoneAssessment(
                zone_id="ZONE-51.5001--0.1001",
                lat=51.5001, lon=-0.1001,
                findings=ZoneFindings(
                    thermal_signatures=3,
                    structural_integrity=0.8,
                    hazards_detected=["smoke"],
                    survivor_count=0,
                ),
                risk_level="high",
                actionable=True,
            )
        ],
        survivor_detections=[SurvivorDetection(lat=51.5002, lon=-0.1002, confidence=0.85)],
        hazard_map=[HazardMarker(lat=51.5, lon=-0.1, type="smoke_plume", exclusion_radius_m=50.0)],
        coverage_pct=73.5,
    )


# ---------------------------------------------------------------------------
# SurveillanceReport round-trip
# ---------------------------------------------------------------------------

def test_surveillance_report_round_trip(surveillance_report):
    json_str = surveillance_report.model_dump_json()
    restored = SurveillanceReport.model_validate_json(json_str)
    assert restored.incident_id == surveillance_report.incident_id
    assert restored.classification == surveillance_report.classification
    assert restored.confidence == surveillance_report.confidence
    assert restored.sensor_summary.thermal_detected is True
    assert restored.sensor_summary.hazard_flags == ["smoke", "high_temp"]


def test_surveillance_report_timestamp_is_utc(surveillance_report):
    assert surveillance_report.timestamp.tzinfo is not None


def test_surveillance_report_carries_prompt_version(surveillance_report):
    assert surveillance_report.prompt_version_hash == "ec1461ee"


# ---------------------------------------------------------------------------
# SwarmFindings round-trip
# ---------------------------------------------------------------------------

def test_swarm_findings_round_trip(swarm_findings):
    json_str = swarm_findings.model_dump_json()
    restored = SwarmFindings.model_validate_json(json_str)
    assert restored.coverage_pct == 73.5
    assert len(restored.zones_assessed) == 1
    assert restored.zones_assessed[0].actionable is True
    assert len(restored.survivor_detections) == 1
    assert restored.survivor_detections[0].confidence == 0.85


# ---------------------------------------------------------------------------
# IncidentBriefing round-trip
# ---------------------------------------------------------------------------

def test_incident_briefing_round_trip(surveillance_report, swarm_findings):
    briefing = IncidentBriefing(
        incident_id="INC-1000000000",
        trigger_type="agent_2_findings_updated",
        surveillance_report=surveillance_report,
        swarm_findings=swarm_findings,
        previous_advisory=None,
    )
    json_str = briefing.model_dump_json()
    restored = IncidentBriefing.model_validate_json(json_str)
    assert restored.incident_id == briefing.incident_id
    assert restored.trigger_type == "agent_2_findings_updated"
    assert restored.swarm_findings.coverage_pct == 73.5
    assert restored.previous_advisory is None


def test_incident_briefing_with_previous_advisory(surveillance_report):
    prev = {"situation_summary": "Fire active", "immediate_actions": ["1. Evacuate"]}
    briefing = IncidentBriefing(
        incident_id="INC-1000000000",
        trigger_type="heartbeat_check",
        surveillance_report=surveillance_report,
        previous_advisory=prev,
    )
    json_str = briefing.model_dump_json()
    restored = IncidentBriefing.model_validate_json(json_str)
    assert restored.previous_advisory["situation_summary"] == "Fire active"


def test_incident_briefing_null_swarm_is_valid(surveillance_report):
    briefing = IncidentBriefing(
        incident_id="INC-1000000000",
        trigger_type="agent_1_report_received",
        surveillance_report=surveillance_report,
        swarm_findings=None,
    )
    assert briefing.swarm_findings is None


# ---------------------------------------------------------------------------
# WorldEvent round-trip
# ---------------------------------------------------------------------------

def test_world_event_round_trip():
    event = WorldEvent(
        incident_id="INC-1000000000",
        trigger_type="fire_grew",
        source="world_state",
        payload={"growth_pct": 15.0},
    )
    json_str = event.model_dump_json()
    restored = WorldEvent.model_validate_json(json_str)
    assert restored.trigger_type == "fire_grew"
    assert restored.payload["growth_pct"] == 15.0
    assert restored.source == "world_state"


# ---------------------------------------------------------------------------
# Validation rejection at the boundary
# ---------------------------------------------------------------------------

def test_surveillance_report_rejects_confidence_above_1():
    with pytest.raises(ValidationError):
        SurveillanceReport(
            incident_id="INC-bad",
            prompt_version_hash="x",
            classification="fire",
            confidence=1.5,
            area=IncidentArea(center={"lat": 0.0, "lon": 0.0}, radius_m=10.0),
            sensor_summary=SensorSummary(
                thermal_detected=False, survivor_probability=0.0,
                hazard_flags=[], wind_speed=0.0, visibility_m=0.0,
            ),
        )


def test_surveillance_report_rejects_bad_classification():
    with pytest.raises(ValidationError):
        SurveillanceReport(
            incident_id="INC-bad",
            prompt_version_hash="x",
            classification="earthquake",  # not in enum
            confidence=0.9,
            area=IncidentArea(center={"lat": 0.0, "lon": 0.0}, radius_m=10.0),
            sensor_summary=SensorSummary(
                thermal_detected=False, survivor_probability=0.0,
                hazard_flags=[], wind_speed=0.0, visibility_m=0.0,
            ),
        )


def test_swarm_findings_rejects_coverage_above_100():
    with pytest.raises(ValidationError):
        SwarmFindings(
            incident_id="INC-bad",
            prompt_version_hash="x",
            zones_assessed=[],
            survivor_detections=[],
            hazard_map=[],
            coverage_pct=150.0,
        )


def test_incident_briefing_rejects_bad_trigger():
    with pytest.raises(ValidationError):
        IncidentBriefing(
            incident_id="INC-bad",
            trigger_type="unknown_event",  # not in Literal
            surveillance_report=None,
        )


def test_hazard_marker_rejects_zero_exclusion_radius():
    with pytest.raises(ValidationError):
        HazardMarker(lat=0.0, lon=0.0, type="chemical", exclusion_radius_m=0.0)
