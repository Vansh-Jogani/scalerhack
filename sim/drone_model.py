"""Kinematic drone model implementing DroneInterface (V1).

Uses great-circle (haversine) math for position updates.
State machine: IDLE -> FLYING -> LOITERING -> RTL -> IDLE
"""

import math
import structlog
from typing import Optional, Tuple

from sim.drone_interface import DroneInterface, Telemetry

logger = structlog.get_logger()


FIXED_WING_DEFAULTS = {
    "cruise_speed": 180.0,   # m/s (10x for demo)
    "cruise_alt": 120.0,    # m AGL
    "loiter_radius": 80.0,  # m
    "turn_radius": 45.0,    # m
}

ROTARY_DEFAULTS = {
    "cruise_speed": 80.0,   # m/s (10x for demo)
    "hover_alt": 30.0,
    "loiter_time": 30.0,
}

MICRO_ROTARY_DEFAULTS = {
    "cruise_speed": 40.0,   # m/s (10x for demo)
    "hover_alt": 10.0,
    "loiter_time": 60.0,
}

# Earth radius in meters
EARTH_RADIUS_M = 6_371_000.0

# Arrival threshold in meters
ARRIVAL_THRESHOLD_M = 5.0


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in meters between two lat/lon points."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return initial bearing in degrees (0-360) from point 1 to point 2."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

    dlon = lon2_r - lon1_r
    x = math.sin(dlon) * math.cos(lat2_r)
    y = (
        math.cos(lat1_r) * math.sin(lat2_r)
        - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    )
    bearing_rad = math.atan2(x, y)
    return (math.degrees(bearing_rad) + 360) % 360


def _destination_point(
    lat: float, lon: float, bearing_deg: float, distance_m: float
) -> Tuple[float, float]:
    """Return (lat, lon) after moving distance_m along bearing from start point."""
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    bearing_r = math.radians(bearing_deg)

    angular_dist = distance_m / EARTH_RADIUS_M

    new_lat_r = math.asin(
        math.sin(lat_r) * math.cos(angular_dist)
        + math.cos(lat_r) * math.sin(angular_dist) * math.cos(bearing_r)
    )
    new_lon_r = lon_r + math.atan2(
        math.sin(bearing_r) * math.sin(angular_dist) * math.cos(lat_r),
        math.cos(angular_dist) - math.sin(lat_r) * math.sin(new_lat_r),
    )

    return math.degrees(new_lat_r), math.degrees(new_lon_r)


class DroneModel(DroneInterface):
    """V1 kinematic drone simulation model.

    Moves toward a target at cruise_speed using great-circle math.
    """

    def __init__(
        self,
        drone_id: str,
        drone_type: str,
        lat: float,
        lon: float,
        alt: float = 0.0,
    ) -> None:
        self.drone_id = drone_id
        self.drone_type = drone_type

        # Current position
        self.lat = lat
        self.lon = lon
        self.alt = alt

        # Home position (for RTL)
        self.home_lat = lat
        self.home_lon = lon
        self.home_alt = alt

        # Target position
        self.target_lat: Optional[float] = None
        self.target_lon: Optional[float] = None
        self.target_alt: Optional[float] = None

        # State machine
        self._state: str = "IDLE"

        # Heading and speed
        self.heading: float = 0.0
        self.speed: float = 0.0

        # Battery simulation (simple linear drain)
        self.battery_pct: float = 100.0

        # Load type-specific defaults
        self._defaults = self._get_defaults(drone_type)
        self.cruise_speed: float = self._defaults["cruise_speed"]

    @staticmethod
    def _get_defaults(drone_type: str) -> dict:
        """Return the defaults dict for the given drone type."""
        if drone_type == "fixed_wing":
            return FIXED_WING_DEFAULTS
        elif drone_type == "rotary":
            return ROTARY_DEFAULTS
        elif drone_type == "micro_rotary":
            return MICRO_ROTARY_DEFAULTS
        else:
            raise ValueError(f"Unknown drone type: {drone_type}")

    def tick(self, dt: float) -> None:
        """Advance simulation by dt seconds."""
        if self._state == "IDLE":
            self.speed = 0.0
            return

        if self._state == "FLYING":
            self._move_toward_target(dt)
            # Check arrival
            if self.target_lat is not None and self.target_lon is not None:
                dist = _haversine_distance(
                    self.lat, self.lon, self.target_lat, self.target_lon
                )
                if dist < ARRIVAL_THRESHOLD_M:
                    self.lat = self.target_lat
                    self.lon = self.target_lon
                    self.alt = self.target_alt if self.target_alt is not None else self.alt
                    self._state = "LOITERING"
                    self.speed = 0.0
                    logger.info("drone_arrived", drone_id=self.drone_id, lat=round(self.lat, 5), lon=round(self.lon, 5), alt=round(self.alt, 1))

        elif self._state == "LOITERING":
            # Hold position; external command can transition out
            self.speed = 0.0

        elif self._state == "RTL":
            self.target_lat = self.home_lat
            self.target_lon = self.home_lon
            self.target_alt = self.home_alt
            self._move_toward_target(dt)
            dist = _haversine_distance(
                self.lat, self.lon, self.home_lat, self.home_lon
            )
            if dist < ARRIVAL_THRESHOLD_M:
                self.lat = self.home_lat
                self.lon = self.home_lon
                self.alt = self.home_alt
                self._state = "IDLE"
                self.speed = 0.0
                logger.info("drone_rtl_complete", drone_id=self.drone_id)
        if self._state != "IDLE":
            self.battery_pct = max(0.0, self.battery_pct - 0.01 * dt)

    def _move_toward_target(self, dt: float) -> None:
        """Move the drone toward its current target using great-circle math."""
        if self.target_lat is None or self.target_lon is None:
            return

        dist = _haversine_distance(
            self.lat, self.lon, self.target_lat, self.target_lon
        )

        if dist < ARRIVAL_THRESHOLD_M:
            return

        # Compute bearing to target
        self.heading = _bearing(
            self.lat, self.lon, self.target_lat, self.target_lon
        )

        # Distance to travel this tick (capped at remaining distance)
        self.speed = self.cruise_speed
        step_distance = min(self.cruise_speed * dt, dist)

        # Compute new position
        new_lat, new_lon = _destination_point(
            self.lat, self.lon, self.heading, step_distance
        )
        self.lat = new_lat
        self.lon = new_lon

        # Linear altitude interpolation toward target
        if self.target_alt is not None and dist > 0:
            alt_diff = self.target_alt - self.alt
            alt_step = alt_diff * (step_distance / dist)
            self.alt += alt_step

    def set_target(self, lat: float, lon: float, alt: float) -> None:
        """Set a new target; transitions from IDLE or LOITERING to FLYING."""
        dist = _haversine_distance(self.lat, self.lon, lat, lon) if self.target_lat else 0
        logger.info("drone_target_set", drone_id=self.drone_id, lat=round(lat, 5), lon=round(lon, 5), alt=alt, dist_m=round(dist, 1))
        self.target_lat = lat
        self.target_lon = lon
        self.target_alt = alt
        if self._state in ("IDLE", "LOITERING"):
            self._state = "FLYING"

    def return_to_launch(self) -> None:
        """Command the drone to return to its home position."""
        logger.info("drone_rtl", drone_id=self.drone_id, from_lat=round(self.lat, 5), from_lon=round(self.lon, 5))
        self._state = "RTL"

    def get_telemetry(self) -> Telemetry:
        """Return current telemetry as a dataclass."""
        return Telemetry(
            drone_id=self.drone_id,
            lat=self.lat,
            lon=self.lon,
            alt=self.alt,
            heading=self.heading,
            speed=self.speed,
            state=self._state,
            battery_pct=self.battery_pct,
            drone_type=self.drone_type,
        )

    def get_state(self) -> str:
        """Return the current state string."""
        return self._state
