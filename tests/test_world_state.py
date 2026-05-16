"""WorldState tests — marker loading, drone management, tick, telemetry format."""

import pytest
from pathlib import Path

from sim.world_state import WorldState, Marker


SCENARIO_PATH = Path(__file__).parent.parent / "sim" / "scenarios" / "fire.json"


def test_empty_world_state():
    ws = WorldState()
    assert ws.get_markers() == []
    assert ws.get_all_telemetry() == []
    assert ws.tick_count == 0


def test_load_scenario_creates_markers(world_with_scenario):
    markers = world_with_scenario.get_markers()
    assert len(markers) >= 1
    for m in markers:
        assert isinstance(m, Marker)
        assert m.id
        assert -90 <= m.lat <= 90
        assert -180 <= m.lon <= 180
        assert m.type in (
            "fire", "structural_collapse", "flood",
            "industrial_hazard", "maritime_sar",
        )
        assert m.severity in ("low", "medium", "high", "critical")

def test_load_scenario_wind_and_events(world_with_scenario):
    wind = world_with_scenario.get_wind()
    assert "speed_ms" in wind
    assert "bearing_deg" in wind
    
    events = world_with_scenario.events
    assert isinstance(events, list)


def test_load_scenario_sets_home_position(world_with_scenario):
    home = world_with_scenario.home_position
    assert "lat" in home and "lon" in home and "alt" in home


def test_add_drone_returns_drone(world):
    drone = world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    assert drone is not None
    assert drone.drone_id == "d1"


def test_add_drone_uses_home_when_no_position_given(world):
    world.home_position = {"lat": 10.0, "lon": 20.0, "alt": 5.0}
    drone = world.add_drone("d1", "fixed_wing")
    assert drone.lat == pytest.approx(10.0)
    assert drone.lon == pytest.approx(20.0)


def test_tick_increments_tick_count(world):
    world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    world.tick(1.0)
    assert world.tick_count == 1
    world.tick(1.0)
    assert world.tick_count == 2


def test_tick_moves_flying_drone(world):
    drone = world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    drone.set_target(0.009, 0.0, 120.0)
    initial_lat = drone.lat
    world.tick(1.0)
    assert drone.lat != initial_lat


def test_command_drone_returns_true_on_valid_id(world):
    world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    result = world.command_drone("d1", 0.009, 0.0, 120.0)
    assert result is True


def test_command_drone_returns_false_on_missing_id(world):
    result = world.command_drone("nonexistent", 0.009, 0.0, 120.0)
    assert result is False


def test_get_all_telemetry_is_list_of_dicts(world):
    world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    telemetry = world.get_all_telemetry()
    assert isinstance(telemetry, list)
    assert len(telemetry) == 1
    t = telemetry[0]
    required_keys = {"drone_id", "lat", "lon", "alt", "heading", "speed", "state", "battery_pct"}
    assert required_keys.issubset(t.keys()), f"Missing keys: {required_keys - t.keys()}"


def test_get_all_telemetry_multiple_drones(world):
    world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    world.add_drone("d2", "rotary", 0.001, 0.001)
    assert len(world.get_all_telemetry()) == 2


def test_get_drone_telemetry_by_id(world):
    world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    t = world.get_drone_telemetry("d1")
    assert t is not None
    assert t.drone_id == "d1"


def test_get_drone_telemetry_unknown_id_returns_none(world):
    assert world.get_drone_telemetry("ghost") is None


def test_multiple_drones_tick_independently(world):
    d1 = world.add_drone("d1", "fixed_wing", 0.0, 0.0)
    d2 = world.add_drone("d2", "fixed_wing", 1.0, 0.0)
    d1.set_target(0.009, 0.0, 120.0)
    # d2 is idle, should not move
    initial_d2_lat = d2.lat
    for _ in range(5):
        world.tick(1.0)
    assert d1.lat != 0.0
    assert d2.lat == initial_d2_lat

def test_tick_processes_events(world):
    world.markers = [Marker(id="m1", lat=0.0, lon=0.0, type="fire", radius_m=100.0, severity="high", confirmed=True)]
    world.events = [{"t_s": 5.0, "type": "fire_growth", "delta_radius_m": 50.0}]
    world.wind = {"speed_ms": 10.0, "bearing_deg": 90.0}
    
    # Tick past 5.0
    world.tick(6.0)
    
    assert len(world.events) == 0
    m = world.markers[0]
    assert m.radius_m == 150.0
    # Center should shift East (90 deg)
    assert m.lon > 0.0
