"""SensorOverlay and flight_tools handler tests."""

import pytest

from sim.sensor_overlay import SensorOverlay, point_in_polygon
from sim.world_state import WorldState
from agents.tools.flight_tools import create_fly_to_handler


# ---------------------------------------------------------------------------
# point_in_polygon
# ---------------------------------------------------------------------------

# Square polygon: corners at (±0.01, ±0.01)
SQUARE = [
    [0.01, -0.01],
    [0.01,  0.01],
    [-0.01, 0.01],
    [-0.01, -0.01],
]


def test_point_inside_polygon():
    assert point_in_polygon(0.0, 0.0, SQUARE) is True


def test_point_outside_polygon():
    assert point_in_polygon(1.0, 1.0, SQUARE) is False


def test_point_on_boundary_treated_consistently():
    # Ray-casting gives a definite answer at boundary; just ensure no crash
    result = point_in_polygon(0.01, 0.0, SQUARE)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# SensorOverlay
# ---------------------------------------------------------------------------

def test_no_reading_without_incident():
    sensor = SensorOverlay()
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    reading = sensor.get_reading("d1", ws)
    assert reading is None


def test_no_reading_outside_polygon():
    sensor = SensorOverlay()
    sensor.set_incident(SQUARE, "fire")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 5.0, 5.0)  # far outside
    reading = sensor.get_reading("d1", ws)
    assert reading is None


def test_fire_reading_inside_polygon():
    sensor = SensorOverlay()
    sensor.set_incident(SQUARE, "fire")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)  # inside polygon
    reading = sensor.get_reading("d1", ws)
    assert reading is not None
    assert reading["thermal_detected"] is True
    assert "active_fire" in reading["hazard_flags"]
    required = {"thermal_detected", "survivor_probability", "hazard_flags", "visibility_m", "wind_speed"}
    assert required.issubset(reading.keys())


def test_structural_collapse_reading():
    sensor = SensorOverlay()
    sensor.set_incident(SQUARE, "structural_collapse")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    reading = sensor.get_reading("d1", ws)
    assert reading is not None
    assert "unstable_structure" in reading["hazard_flags"]


def test_flood_reading():
    sensor = SensorOverlay()
    sensor.set_incident(SQUARE, "flood")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    reading = sensor.get_reading("d1", ws)
    assert reading is not None
    assert reading["thermal_detected"] is False
    assert "rising_water" in reading["hazard_flags"]


def test_unknown_drone_returns_none():
    sensor = SensorOverlay()
    sensor.set_incident(SQUARE, "fire")
    ws = WorldState()
    reading = sensor.get_reading("ghost_drone", ws)
    assert reading is None


# ---------------------------------------------------------------------------
# fly_to handler (T2.3 / Checkpoint 6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fly_to_valid_drone():
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    handler = create_fly_to_handler(ws)
    result = await handler(drone_id="d1", lat=0.009, lon=0.0, alt=120.0)
    assert result["status"] == "ok"
    assert ws.drones["d1"].get_state() == "FLYING"


@pytest.mark.asyncio
async def test_fly_to_unknown_drone_returns_error():
    ws = WorldState()
    handler = create_fly_to_handler(ws)
    result = await handler(drone_id="ghost", lat=0.009, lon=0.0, alt=120.0)
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_fly_to_updates_drone_position_after_tick():
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", 0.0, 0.0)
    handler = create_fly_to_handler(ws)
    await handler(drone_id="d1", lat=0.009, lon=0.0, alt=120.0)
    initial_lat = ws.drones["d1"].lat
    ws.tick(1.0)
    assert ws.drones["d1"].lat != initial_lat
