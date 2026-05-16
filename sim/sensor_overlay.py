"""Synthetic sensor returns — radius-based (per CHANGE 3, 2026-05-15)."""

import structlog

from sim.math_utils import haversine_distance

logger = structlog.get_logger()


def point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    """Ray-casting point-in-polygon check."""
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        if (polygon[i][1] > lon) != (polygon[j][1] > lon) and lat < (
            (polygon[j][0] - polygon[i][0])
            * (lon - polygon[i][1])
            / (polygon[j][1] - polygon[i][1])
            + polygon[i][0]
        ):
            inside = not inside
        j = i
    return inside


_SENSOR_RETURNS: dict[str, dict] = {
    "fire": {
        "thermal_detected": True,
        "survivor_probability": 0.3,
        "hazard_flags": ["active_fire", "smoke"],
        "visibility_m": 200.0,
        "wind_speed": 12.0,
    },
    "structural_collapse": {
        "thermal_detected": True,
        "survivor_probability": 0.6,
        "hazard_flags": ["unstable_structure"],
        "visibility_m": 5000.0,
        "wind_speed": 5.0,
    },
    "flood": {
        "thermal_detected": False,
        "survivor_probability": 0.4,
        "hazard_flags": ["rising_water"],
        "visibility_m": 3000.0,
        "wind_speed": 8.0,
    },
    "industrial_hazard": {
        "thermal_detected": True,
        "survivor_probability": 0.1,
        "hazard_flags": ["toxic_gas", "explosion_risk"],
        "visibility_m": 500.0,
        "wind_speed": 6.0,
    },
    "maritime_sar": {
        "thermal_detected": True,
        "survivor_probability": 0.5,
        "hazard_flags": ["rough_seas"],
        "visibility_m": 4000.0,
        "wind_speed": 20.0,
    },
}

_FALLBACK_RETURN = {
    "thermal_detected": False,
    "survivor_probability": 0.0,
    "hazard_flags": [],
    "visibility_m": 10000.0,
    "wind_speed": 5.0,
}


class SensorOverlay:
    def __init__(self) -> None:
        self.center_lat: float | None = None
        self.center_lon: float | None = None
        self.radius_m: float = 600.0
        self.disaster_type: str | None = None

    def set_incident(
        self,
        center_lat: float,
        center_lon: float,
        radius_m: float,
        disaster_type: str,
    ) -> None:
        """Set active incident as center+radius (replaces polygon check)."""
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.radius_m = radius_m
        self.disaster_type = disaster_type

    def get_reading(self, drone_id: str, world_state) -> dict | None:
        """Return sensor data if drone is within incident radius, else None.

        Returned dict includes distance_m and intensity (0.0–1.0, strongest at
        center) so agents can reason about proximity to the incident.
        """
        if self.center_lat is None or self.disaster_type is None:
            return None

        telemetry = world_state.get_drone_telemetry(drone_id)
        if telemetry is None:
            return None

        dist = haversine_distance(
            telemetry.lat, telemetry.lon, self.center_lat, self.center_lon
        )
        if dist > self.radius_m:
            return None

        base = _SENSOR_RETURNS.get(self.disaster_type)
        if base is None:
            logger.warning(
                "sensor_overlay_unknown_type",
                disaster_type=self.disaster_type,
                drone_id=drone_id,
            )
            base = _FALLBACK_RETURN

        intensity = round(1.0 - (dist / self.radius_m), 3)
        return {
            **base,
            "distance_m": round(dist, 1),
            "intensity": intensity,
        }
