"""Tests for the prompt registry (Deliverable 1)."""

import hashlib
import pytest
from pathlib import Path

from prompts import load_prompt, fill_template, list_prompts


# ---------------------------------------------------------------------------
# load_prompt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["agent1_surveillance", "agent2_specialist", "agent3_advisory"])
def test_all_agent_prompts_load(name):
    entry = load_prompt(name)
    assert isinstance(entry["text"], str)
    assert len(entry["text"]) > 100, f"{name} prompt suspiciously short"
    assert isinstance(entry["version_hash"], str)
    assert len(entry["version_hash"]) == 8


def test_version_hash_is_sha256_prefix():
    entry = load_prompt("agent1_surveillance")
    full = hashlib.sha256(entry["text"].encode()).hexdigest()
    assert full.startswith(entry["version_hash"])


def test_missing_prompt_raises():
    with pytest.raises(FileNotFoundError, match="not found"):
        load_prompt("nonexistent_prompt_xyz")


def test_load_prompt_is_cached():
    a = load_prompt("agent1_surveillance")
    b = load_prompt("agent1_surveillance")
    assert a is b


def test_reload_bypasses_cache():
    a = load_prompt("agent3_advisory")
    b = load_prompt("agent3_advisory", reload=True)
    assert a["text"] == b["text"]   # same content
    assert a is not b               # different object


# ---------------------------------------------------------------------------
# Includes resolved at load time
# ---------------------------------------------------------------------------

def test_includes_resolved_in_agent1():
    entry = load_prompt("agent1_surveillance")
    assert "{{include:" not in entry["text"], "unresolved include directive found"
    # safety_rules content should be present
    assert "60 m AGL" in entry["text"] or "60" in entry["text"]


def test_includes_resolved_in_agent2():
    entry = load_prompt("agent2_specialist")
    assert "{{include:" not in entry["text"]


def test_includes_resolved_in_agent3():
    entry = load_prompt("agent3_advisory")
    assert "{{include:" not in entry["text"]


def test_no_circular_include_explosion():
    """Registry must not hang or stack-overflow on valid prompts."""
    for name in list_prompts():
        load_prompt(name)  # must complete


# ---------------------------------------------------------------------------
# fill_template
# ---------------------------------------------------------------------------

def test_fill_template_replaces_known_vars():
    template = "Hello {{name}}, you have {{count}} drones."
    result = fill_template(template, name="ARIA", count="3")
    assert result == "Hello ARIA, you have 3 drones."


def test_fill_template_leaves_unknown_vars():
    template = "Known: {{known}}. Unknown: {{unknown}}."
    result = fill_template(template, known="yes")
    assert "Unknown: {{unknown}}" in result
    assert "Known: yes" in result


def test_fill_template_on_agent2_prompt():
    entry = load_prompt("agent2_specialist")
    filled = fill_template(
        entry["text"],
        swarm_type="thermal_rotary",
        drone_count="3",
        sensors="thermal_camera, gas_detector",
        altitude="50",
        constraint="maintain_upwind_position",
        priority_tasks="1. map fire perimeter\n2. identify hotspots",
    )
    assert "thermal_rotary" in filled
    assert "{{swarm_type}}" not in filled
    assert "{{drone_count}}" not in filled


# ---------------------------------------------------------------------------
# list_prompts
# ---------------------------------------------------------------------------

def test_list_prompts_returns_agent_names():
    names = list_prompts()
    assert "agent1_surveillance" in names
    assert "agent2_specialist" in names
    assert "agent3_advisory" in names


def test_list_prompts_excludes_shared():
    names = list_prompts()
    for name in names:
        assert not name.startswith("_"), f"_shared file leaked into list_prompts: {name}"
