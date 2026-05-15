"""Tests for tool schemas (Deliverable 2)."""

import json
import pytest

from agents.tools.schemas import (
    FlyToInput, LoiterOverInput, GetSensorReadingInput,
    ReportClassificationInput, RequestDetailedPassInput,
    DeploySwarmInput, UpdateZoneClassificationInput,
    MarkSurvivorInput, MarkHazardInput, ReportSwarmFindingsInput,
    IssueAdvisoryInput,
    AGENT_1_TOOLS, AGENT_2_TOOLS, AGENT_3_TOOLS,
)


# ---------------------------------------------------------------------------
# to_claude_tool_dict structure
# ---------------------------------------------------------------------------

ALL_TOOL_CLASSES = [
    FlyToInput, LoiterOverInput, GetSensorReadingInput,
    ReportClassificationInput, RequestDetailedPassInput,
    DeploySwarmInput, UpdateZoneClassificationInput,
    MarkSurvivorInput, MarkHazardInput, ReportSwarmFindingsInput,
    IssueAdvisoryInput,
]

@pytest.mark.parametrize("cls", ALL_TOOL_CLASSES)
def test_tool_dict_has_required_claude_fields(cls):
    d = cls.to_claude_tool_dict()
    assert "name" in d and d["name"], f"{cls.__name__} missing name"
    assert "description" in d and d["description"], f"{cls.__name__} missing description"
    assert "input_schema" in d, f"{cls.__name__} missing input_schema"
    assert d["input_schema"]["type"] == "object"


@pytest.mark.parametrize("cls", ALL_TOOL_CLASSES)
def test_no_title_keys_in_schema(cls):
    schema_json = json.dumps(cls.to_claude_tool_dict())
    assert '"title"' not in schema_json, f"{cls.__name__} has title key that Claude API doesn't need"


def test_agent_tool_lists_coverage():
    assert len(AGENT_1_TOOLS) == 5
    assert len(AGENT_2_TOOLS) == 6
    assert len(AGENT_3_TOOLS) == 1


def test_agent_tool_names_are_unique_per_agent():
    for tool_list, label in [(AGENT_1_TOOLS, "A1"), (AGENT_2_TOOLS, "A2"), (AGENT_3_TOOLS, "A3")]:
        names = [t["name"] for t in tool_list]
        assert len(names) == len(set(names)), f"Duplicate tool names in {label}: {names}"


# ---------------------------------------------------------------------------
# validate_call — happy path
# ---------------------------------------------------------------------------

def test_fly_to_valid():
    obj, err = FlyToInput.validate_call({"drone_id": "d1", "lat": 51.5, "lon": -0.1, "alt": 120.0})
    assert obj is not None
    assert err is None


def test_loiter_over_valid():
    obj, err = LoiterOverInput.validate_call({"drone_id": "d1", "lat": 51.5, "lon": -0.1, "radius_m": 80.0, "duration_s": 60.0})
    assert obj is not None and err is None


def test_deploy_swarm_valid():
    obj, err = DeploySwarmInput.validate_call({
        "positions": [
            {"drone_id": "s1", "lat": 51.5, "lon": -0.1, "alt": 50.0},
            {"drone_id": "s2", "lat": 51.51, "lon": -0.11, "alt": 50.0},
        ]
    })
    assert obj is not None and err is None


def test_issue_advisory_valid():
    obj, err = IssueAdvisoryInput.validate_call({
        "situation_summary": "Fire confirmed at sector 7.",
        "immediate_actions": ["1. Evacuate block north of marker"],
        "exclusion_zones": [{"lat": 51.5, "lon": -0.1, "radius_m": 100.0, "reason": "active fire"}],
        "resource_requirements": ["3 fire engines", "Incident commander"],
        "risk_flags": ["Wind shift may expand fire eastward"],
        "monitoring_status": "Thermal swarm at 50m, 30s refresh",
    })
    assert obj is not None and err is None


# ---------------------------------------------------------------------------
# validate_call — boundary enforcement (sad path)
# ---------------------------------------------------------------------------

def test_fly_to_rejects_alt_below_60m():
    obj, err = FlyToInput.validate_call({"drone_id": "d1", "lat": 51.5, "lon": -0.1, "alt": 30.0})
    assert obj is None
    assert err is not None


def test_fly_to_rejects_missing_drone_id():
    obj, err = FlyToInput.validate_call({"lat": 51.5, "lon": -0.1, "alt": 120.0})
    assert obj is None and err is not None


def test_report_classification_rejects_bad_enum():
    obj, err = ReportClassificationInput.validate_call({
        "incident_id": "INC-001",
        "classification": "earthquake",  # not in enum
        "confidence": 0.9,
        "area": {"center": {"lat": 51.5, "lon": -0.1}, "radius_m": 100.0},
        "sensor_summary": {
            "thermal_detected": True, "survivor_probability": 0.5,
            "hazard_flags": [], "wind_speed": 3.0, "visibility_m": 500.0,
        },
    })
    assert obj is None and err is not None


def test_confidence_rejects_above_1():
    _, err = FlyToInput.validate_call({"drone_id": "d1", "lat": 0.0, "lon": 0.0, "alt": 120.0})
    # FlyTo has no confidence — use ReportClassification
    obj, err = ReportClassificationInput.validate_call({
        "incident_id": "INC-001",
        "classification": "fire",
        "confidence": 1.5,  # invalid
        "area": {"center": {"lat": 0.0, "lon": 0.0}, "radius_m": 50.0},
        "sensor_summary": {
            "thermal_detected": True, "survivor_probability": 0.0,
            "hazard_flags": [], "wind_speed": 0.0, "visibility_m": 0.0,
        },
    })
    assert obj is None and err is not None


def test_deploy_swarm_rejects_empty_positions():
    obj, err = DeploySwarmInput.validate_call({"positions": []})
    assert obj is None and err is not None


def test_issue_advisory_rejects_too_many_actions():
    obj, err = IssueAdvisoryInput.validate_call({
        "situation_summary": "X",
        "immediate_actions": ["1", "2", "3", "4", "5", "6"],  # max 5
        "exclusion_zones": [],
        "resource_requirements": [],
        "risk_flags": [],
        "monitoring_status": "active",
    })
    assert obj is None and err is not None


# ---------------------------------------------------------------------------
# Malformed call returns typed error string, not an exception
# ---------------------------------------------------------------------------

def test_validate_call_returns_error_string_not_exception():
    obj, err = FlyToInput.validate_call({"drone_id": "d1"})  # missing lat, lon, alt
    assert obj is None
    assert isinstance(err, str)
    assert len(err) > 0
