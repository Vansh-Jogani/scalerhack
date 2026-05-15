"""Shared fixtures for ARIA v1 tests."""

import pytest
from pathlib import Path

from sim.world_state import WorldState
from sim.sensor_overlay import SensorOverlay


SCENARIO_PATH = Path(__file__).parent.parent / "sim" / "scenarios" / "fire.json"

# A simple square polygon centred at (0, 0), side ~2km
SQUARE_POLYGON = [
    [0.01, -0.01],
    [0.01,  0.01],
    [-0.01, 0.01],
    [-0.01, -0.01],
]


@pytest.fixture
def world():
    ws = WorldState()
    ws.home_position = {"lat": 0.0, "lon": 0.0, "alt": 0.0}
    return ws


@pytest.fixture
def world_with_scenario():
    return WorldState(SCENARIO_PATH)


@pytest.fixture
def sensor():
    return SensorOverlay()
