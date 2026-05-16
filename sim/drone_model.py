"""Kinematic drone model implementing DroneInterface (V1).

Uses great-circle (haversine) math for position updates.
State machine: IDLE -> FLYING -> LOITERING -> RTL -> IDLE
"""

from typing import Optional

from sim.drone_interface import DroneInterface, Telemetry
from sim.math_utils import haversine_distance as _haversine_distance
from sim.math_utils import bearing as _bearing
from sim.math_utils import destination_point as _destination_point

FIXED_WING_DEFAULTS = {
    "cruise_speed": 60.0,   # m/s — fast recon
    "cruise_alt": 120.0,    # m AGL
    "loiter_radius": 80.0,  # m
    "turn_radius": 45.0,    # m
}

ROTARY_DEFAULTS = {
    "cruise_speed": 26.0,   # m/s — fast transit for demo
    "hover_alt": 30.0,
    "loiter_time": 30.0,
}

MICRO_ROTARY_DEFAULTS = {
    "cruise_speed": 20.0,   # m/s
    "hover_alt": 10.0,
    "loiter_time": 60.0,
}


# Arrival threshold in meters
ARRIVAL_THRESHOLD_M = 5.0


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

        # Simple battery drain: 0.01% per second while not idle
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
        """Set a new target; transitions from IDLE or LOITERING to FLYING.

        Does NOT interrupt RTL — a drone in RTL must complete its return before
        it accepts a new target. This is intentional: RTL is a safety-priority
        state and agents should not override it.
        """
        self.target_lat = lat
        self.target_lon = lon
        self.target_alt = alt
        if self._state in ("IDLE", "LOITERING"):
            self._state = "FLYING"

    def return_to_launch(self) -> None:
        """Command the drone to return to its home position."""
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
