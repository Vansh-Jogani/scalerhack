"""T4.1 — base_agent observe/reason/act loop (Anthropic client mocked)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from agents.base_agent import BaseAgent
from sim.world_state import WorldState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_agent(world_state) -> BaseAgent:
    from sim.sensor_overlay import SensorOverlay
    return BaseAgent(
        agent_id="test-agent",
        system_prompt="You are a test agent.",
        model="claude-sonnet-4-20250514",
        world_state=world_state,
        sensor_overlay=SensorOverlay(),
        drone_ids=["d1"],
        tools=[],
        tool_handlers={},
        interval=0.01,
    )


def _tool_use_block(name: str, tool_id: str, input_data: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = tool_id
    block.input = input_data
    return block


def _text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


# ---------------------------------------------------------------------------
# Observe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_observe_returns_markers_and_telemetry():
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    agent = make_agent(ws)
    obs = await agent.observe()
    assert "markers" in obs
    assert "drone_telemetry" in obs
    assert isinstance(obs["markers"], list)
    assert isinstance(obs["drone_telemetry"], list)
    assert len(obs["drone_telemetry"]) == 1


@pytest.mark.asyncio
async def test_observe_telemetry_is_none_for_missing_drone():
    ws = WorldState()
    # Agent references drone "d1" but it doesn't exist yet
    agent = make_agent(ws)
    obs = await agent.observe()
    # BaseAgent.observe() skips drones with no telemetry — list is empty
    assert obs["drone_telemetry"] == []


# ---------------------------------------------------------------------------
# Act — tool execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_act_executes_registered_tool():
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    agent = make_agent(ws)

    called_with = {}

    async def fake_fly_to(**kwargs):
        called_with.update(kwargs)
        return {"status": "ok"}

    agent.register_tool("fly_to", fake_fly_to)

    response = MagicMock()
    response.content = [
        _tool_use_block("fly_to", "tu_001", {"drone_id": "d1", "lat": 0.009, "lon": 0.0, "alt": 120.0})
    ]

    results = await agent.act(response)
    assert len(results) == 1
    assert results[0]["tool"] == "fly_to"
    assert results[0]["result"]["status"] == "ok"
    assert called_with["drone_id"] == "d1"


@pytest.mark.asyncio
async def test_act_skips_unknown_tool():
    ws = WorldState()
    agent = make_agent(ws)

    response = MagicMock()
    response.content = [
        _tool_use_block("nonexistent_tool", "tu_002", {})
    ]

    results = await agent.act(response)
    # Unknown tools return an error result, not an empty list
    assert len(results) == 1
    assert results[0]["result"]["status"] == "error"


@pytest.mark.asyncio
async def test_act_ignores_text_blocks():
    ws = WorldState()
    agent = make_agent(ws)

    response = MagicMock()
    response.content = [_text_block("I will now fly to the target.")]

    results = await agent.act(response)
    assert results == []


@pytest.mark.asyncio
async def test_act_multiple_tools_in_one_response():
    ws = WorldState()
    agent = make_agent(ws)
    calls = []

    async def handler(**kwargs):
        calls.append(kwargs)
        return {"status": "ok"}

    agent.register_tool("fly_to", handler)
    agent.register_tool("get_sensor_reading", handler)

    response = MagicMock()
    response.content = [
        _tool_use_block("fly_to", "tu_001", {"drone_id": "d1", "lat": 0.0, "lon": 0.0, "alt": 120.0}),
        _tool_use_block("get_sensor_reading", "tu_002", {"drone_id": "d1"}),
    ]

    results = await agent.act(response)
    assert len(results) == 2
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Full observe→reason→act cycle (mocked Anthropic)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_one_cycle_with_mocked_client():
    """Observe→reason→act cycle using the real fly_to handler to verify state update."""
    from agents.tools.flight_tools import create_fly_to_handler

    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    agent = make_agent(ws)

    # Register the real handler so world state actually changes
    agent.register_tool("fly_to", create_fly_to_handler(ws))

    mock_response = MagicMock()
    mock_response.content = [
        _tool_use_block("fly_to", "tu_001", {"drone_id": "d1", "lat": 0.009, "lon": 0.0, "alt": 120.0})
    ]

    agent.client = AsyncMock()
    agent.client.messages.create = AsyncMock(return_value=mock_response)

    obs = await agent.observe()
    response = await agent.reason(obs)
    results = await agent.act(response)

    assert results[0]["result"]["status"] == "ok"
    assert ws.drones["d1"].get_state() == "FLYING"
