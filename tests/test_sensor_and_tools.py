"""SensorOverlay and flight_tools handler tests — radius-based API."""

import math
import pytest

from sim.sensor_overlay import SensorOverlay, point_in_polygon
from sim.world_state import WorldState
from agents.tools.flight_tools import create_fly_to_handler


# ---------------------------------------------------------------------------
# point_in_polygon (utility function — still exists)
# ---------------------------------------------------------------------------

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
    result = point_in_polygon(0.01, 0.0, SQUARE)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# SensorOverlay — radius-based API
# ---------------------------------------------------------------------------

# Centre at (17.395, 78.496), radius 600 m
_LAT = 17.395
_LON = 78.496
_RAD = 600.0


def _drone_at(ws: WorldState, lat: float, lon: float) -> None:
    ws.add_drone("d1", "fixed_wing", lat, lon)


def test_no_reading_without_incident():
    sensor = SensorOverlay()
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", _LAT, _LON)
    assert sensor.get_reading("d1", ws) is None


def test_no_reading_outside_radius():
    sensor = SensorOverlay()
    sensor.set_incident(_LAT, _LON, _RAD, "fire")
    ws = WorldState()
    # 5 km away — well outside 600 m radius
    ws.add_drone("d1", "fixed_wing", _LAT + 0.05, _LON + 0.05)
    assert sensor.get_reading("d1", ws) is None


def test_fire_reading_inside_radius():
    sensor = SensorOverlay()
    sensor.set_incident(_LAT, _LON, _RAD, "fire")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", _LAT, _LON)  # exactly at centre
    reading = sensor.get_reading("d1", ws)
    assert reading is not None
    assert reading["thermal_detected"] is True
    assert "active_fire" in reading["hazard_flags"]
    required = {"thermal_detected", "survivor_probability", "hazard_flags", "visibility_m", "wind_speed"}
    assert required.issubset(reading.keys())


def test_structural_collapse_reading():
    sensor = SensorOverlay()
    sensor.set_incident(_LAT, _LON, _RAD, "structural_collapse")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", _LAT, _LON)
    reading = sensor.get_reading("d1", ws)
    assert reading is not None
    assert "unstable_structure" in reading["hazard_flags"]


def test_flood_reading():
    sensor = SensorOverlay()
    sensor.set_incident(_LAT, _LON, _RAD, "flood")
    ws = WorldState()
    ws.add_drone("d1", "fixed_wing", _LAT, _LON)
    reading = sensor.get_reading("d1", ws)
    assert reading is not None
    assert reading["thermal_detected"] is False
    assert "rising_water" in reading["hazard_flags"]


def test_unknown_drone_returns_none():
    sensor = SensorOverlay()
    sensor.set_incident(_LAT, _LON, _RAD, "fire")
    ws = WorldState()
    assert sensor.get_reading("ghost_drone", ws) is None


def test_reading_at_exact_boundary():
    """Drone exactly at radius_m distance — should return data."""
    sensor = SensorOverlay()
    sensor.set_incident(_LAT, _LON, _RAD, "fire")
    ws = WorldState()
    # Place drone ~599 m north (inside)
    lat_offset = 599.0 / 111320.0
    ws.add_drone("d1", "fixed_wing", _LAT + lat_offset, _LON)
    reading = sensor.get_reading("d1", ws)
    assert reading is not None


# ---------------------------------------------------------------------------
# fly_to handler
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
