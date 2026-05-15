"""Synthetic sensor returns based on drone proximity to incident center."""

import math

EARTH_RADIUS_M = 6_371_000.0


def _haversine(lat1, lon1, lat2, lon2) -> float:
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def point_in_polygon(lat, lon, polygon):
    """Ray casting point-in-polygon (kept for backwards compat with tests)."""
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        if ((polygon[i][1] > lon) != (polygon[j][1] > lon) and
            lat < (polygon[j][0] - polygon[i][0]) *
            (lon - polygon[i][1]) /
            (polygon[j][1] - polygon[i][1]) + polygon[i][0]):
            inside = not inside
        j = i
    return inside


_SENSOR_DATA = {
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
    def __init__(self):
        self.center_lat: float | None = None
        self.center_lon: float | None = None
        self.radius_m: float = 500.0
        self.disaster_type: str | None = None

    def set_incident(self, center: dict, radius_m: float, disaster_type: str):
        """Configure the active incident zone (center + radius, radius-based detection)."""
        self.center_lat = center["lat"]
        self.center_lon = center["lon"]
        self.radius_m = radius_m
        self.disaster_type = disaster_type

    def get_reading(self, drone_id: str, world_state) -> dict | None:
        """Return sensor data if drone is within incident radius, None otherwise."""
        if self.center_lat is None or self.disaster_type is None:
            return None

        telemetry = world_state.get_drone_telemetry(drone_id)
        if telemetry is None:
            return None

        dist = _haversine(telemetry.lat, telemetry.lon, self.center_lat, self.center_lon)
        if dist > self.radius_m:
            return None

        return _SENSOR_DATA.get(self.disaster_type, {
            "thermal_detected": False,
            "survivor_probability": 0.0,
            "hazard_flags": [],
            "visibility_m": 10000.0,
            "wind_speed": 5.0,
        })
