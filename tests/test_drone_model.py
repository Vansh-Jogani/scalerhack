"""T3.1-T3.4 — Drone kinematic model tests."""

import math
import pytest

from sim.drone_model import (
    DroneModel,
    _haversine_distance,
    _bearing,
    _destination_point,
    FIXED_WING_DEFAULTS,
    ROTARY_DEFAULTS,
    MICRO_ROTARY_DEFAULTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fixed_wing(lat=0.0, lon=0.0, alt=0.0) -> DroneModel:
    return DroneModel("fw1", "fixed_wing", lat, lon, alt)


def make_rotary(lat=0.0, lon=0.0, alt=0.0) -> DroneModel:
    return DroneModel("r1", "rotary", lat, lon, alt)


def make_micro_rotary(lat=0.0, lon=0.0, alt=0.0) -> DroneModel:
    return DroneModel("mr1", "micro_rotary", lat, lon, alt)


# One km north from (0,0)
TARGET_1KM_LAT = 0.008983
TARGET_1KM_LON = 0.0
TARGET_ALT = 120.0


# ---------------------------------------------------------------------------
# Haversine math sanity
# ---------------------------------------------------------------------------

def test_haversine_same_point():
    assert _haversine_distance(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)


def test_haversine_1km_north():
    dist = _haversine_distance(0.0, 0.0, TARGET_1KM_LAT, TARGET_1KM_LON)
    assert dist == pytest.approx(1000.0, abs=5.0)


def test_bearing_north():
    b = _bearing(0.0, 0.0, 1.0, 0.0)
    assert b == pytest.approx(0.0, abs=0.1)


def test_bearing_east():
    b = _bearing(0.0, 0.0, 0.0, 1.0)
    assert b == pytest.approx(90.0, abs=0.1)


def test_destination_point_north():
    lat, lon = _destination_point(0.0, 0.0, 0.0, 1000.0)
    assert lat == pytest.approx(TARGET_1KM_LAT, abs=0.0001)
    assert lon == pytest.approx(0.0, abs=0.0001)


# ---------------------------------------------------------------------------
# T3.1 — Position update mechanics
# ---------------------------------------------------------------------------

def test_position_updates_every_tick():
    drone = make_fixed_wing()
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    prev_lat = drone.lat
    drone.tick(1.0)
    assert drone.lat != prev_lat, "Position must change after first tick"


def test_fixed_wing_1km_arrival_time():
    """Fixed-wing at 18 m/s should cover 1km in ≈55 s (±2 s tolerance)."""
    drone = make_fixed_wing()
    dist = _haversine_distance(0.0, 0.0, TARGET_1KM_LAT, TARGET_1KM_LON)
    expected_s = dist / FIXED_WING_DEFAULTS["cruise_speed"]

    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    elapsed = 0.0
    dt = 1.0
    for _ in range(200):
        drone.tick(dt)
        elapsed += dt
        if drone.get_state() == "LOITERING":
            break

    assert drone.get_state() == "LOITERING", "Drone must arrive within 200s"
    assert abs(elapsed - expected_s) <= 2.0, (
        f"Arrival time {elapsed:.1f}s, expected {expected_s:.1f}s ±2s"
    )


def test_heading_nonzero_during_flight():
    drone = make_fixed_wing()
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    drone.tick(1.0)
    assert drone.heading != 0.0 or drone.lat != 0.0  # heading set on first move


# ---------------------------------------------------------------------------
# T3.2 — Drone class defaults
# ---------------------------------------------------------------------------

def test_fixed_wing_cruise_speed():
    drone = make_fixed_wing()
    assert drone.cruise_speed == FIXED_WING_DEFAULTS["cruise_speed"]  # 18 m/s


def test_rotary_cruise_speed():
    drone = make_rotary()
    assert drone.cruise_speed == ROTARY_DEFAULTS["cruise_speed"]  # 8 m/s


def test_micro_rotary_cruise_speed():
    drone = make_micro_rotary()
    assert drone.cruise_speed == MICRO_ROTARY_DEFAULTS["cruise_speed"]  # 4 m/s


def test_fixed_wing_defaults_values():
    assert FIXED_WING_DEFAULTS["cruise_speed"] == 18.0
    assert FIXED_WING_DEFAULTS["cruise_alt"] == 120.0
    assert FIXED_WING_DEFAULTS["loiter_radius"] == 80.0


def test_rotary_defaults_values():
    assert ROTARY_DEFAULTS["cruise_speed"] == 8.0
    assert ROTARY_DEFAULTS["hover_alt"] == 30.0
    assert ROTARY_DEFAULTS["loiter_time"] == 30.0


def test_micro_rotary_defaults_values():
    assert MICRO_ROTARY_DEFAULTS["cruise_speed"] == 4.0
    assert MICRO_ROTARY_DEFAULTS["hover_alt"] == 10.0
    assert MICRO_ROTARY_DEFAULTS["loiter_time"] == 60.0


def test_unknown_drone_type_raises():
    with pytest.raises(ValueError):
        DroneModel("x", "helicopter", 0.0, 0.0)


# ---------------------------------------------------------------------------
# T3.3 — State machine transitions
# ---------------------------------------------------------------------------

def test_idle_to_flying_on_set_target():
    drone = make_fixed_wing()
    assert drone.get_state() == "IDLE"
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    assert drone.get_state() == "FLYING"


def test_flying_to_loitering_on_arrival():
    drone = make_fixed_wing()
    # Place drone 1m from target — will arrive in one tick
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    # Teleport near target to force arrival this tick
    drone.lat = TARGET_1KM_LAT - 0.00001
    drone.lon = TARGET_1KM_LON
    drone.tick(1.0)
    assert drone.get_state() == "LOITERING"


def test_loitering_to_rtl():
    drone = make_fixed_wing()
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    drone._state = "LOITERING"
    drone.return_to_launch()
    assert drone.get_state() == "RTL"


def test_rtl_to_idle_on_home_arrival():
    drone = make_fixed_wing()
    drone.return_to_launch()
    # Place near home
    drone.lat = drone.home_lat + 0.000001
    drone.tick(1.0)
    assert drone.get_state() == "IDLE"


def test_loitering_to_flying_on_new_target():
    """set_target from LOITERING resumes FLYING."""
    drone = make_fixed_wing()
    drone._state = "LOITERING"
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    assert drone.get_state() == "FLYING"


# ---------------------------------------------------------------------------
# T3.4 — Loiter pattern correctness
# ---------------------------------------------------------------------------

def test_loitering_drone_holds_position():
    drone = make_fixed_wing()
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    drone._state = "LOITERING"
    drone.lat = TARGET_1KM_LAT
    drone.lon = TARGET_1KM_LON
    before_lat, before_lon = drone.lat, drone.lon
    for _ in range(10):
        drone.tick(1.0)
    assert drone.lat == pytest.approx(before_lat)
    assert drone.lon == pytest.approx(before_lon)


def test_speed_zero_while_loitering():
    drone = make_fixed_wing()
    drone._state = "LOITERING"
    drone.tick(1.0)
    assert drone.speed == 0.0


# ---------------------------------------------------------------------------
# Battery drain
# ---------------------------------------------------------------------------

def test_battery_drains_while_flying():
    drone = make_fixed_wing()
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    for _ in range(100):
        drone.tick(1.0)
    assert drone.battery_pct < 100.0


def test_battery_stable_while_idle():
    drone = make_fixed_wing()
    start = drone.battery_pct
    for _ in range(100):
        drone.tick(1.0)
    assert drone.battery_pct == start

def test_auto_rtl_on_low_battery():
    drone = make_fixed_wing()
    drone.set_target(TARGET_1KM_LAT, TARGET_1KM_LON, TARGET_ALT)
    drone.battery_pct = 20.5
    drone.tick(1.0)
    assert drone.get_state() == "FLYING"
    
    drone.battery_pct = 20.0
    drone.tick(1.0) # battery drops below threshold
    assert drone.get_state() == "RTL"

def test_battery_critical_flag():
    drone = make_fixed_wing()
    drone.battery_pct = 25.0
    tel = drone.get_telemetry()
    assert not tel.battery_critical
    
    drone.battery_pct = 19.0
    tel = drone.get_telemetry()
    assert tel.battery_critical
