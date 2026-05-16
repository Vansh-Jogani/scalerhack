"""Synthetic sensor returns — radius-based (per CHANGE 3, 2026-05-15)."""

import math


def point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    """Ray-casting point-in-polygon check (kept for utility use)."""
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


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
        "visibility_m": 8000.0,
        "wind_speed": 20.0,
    },
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
        """Return sensor data if drone is within incident radius, else None."""
        if self.center_lat is None or self.disaster_type is None:
            return None

        telemetry = world_state.get_drone_telemetry(drone_id)
        if telemetry is None:
            return None

        dist = _haversine(
            telemetry.lat, telemetry.lon, self.center_lat, self.center_lon
        )
        if dist > self.radius_m:
            return None

        return _SENSOR_RETURNS.get(
            self.disaster_type,
            {
                "thermal_detected": False,
                "survivor_probability": 0.0,
                "hazard_flags": [],
                "visibility_m": 10000.0,
                "wind_speed": 5.0,
            },
        )
