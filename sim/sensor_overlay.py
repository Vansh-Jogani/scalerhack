"""Synthetic sensor returns based on drone position vs incident boundary polygon."""


def point_in_polygon(lat, lon, polygon):
    """Ray casting algorithm for point-in-polygon check."""
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


class SensorOverlay:
    def __init__(self):
        self.boundary_polygon = None
        self.disaster_type = None

    def set_incident(self, boundary_polygon: list, disaster_type: str):
        """Set active incident polygon and type (called by orchestrator on GO)."""
        self.boundary_polygon = boundary_polygon
        self.disaster_type = disaster_type

    def get_reading(self, drone_id: str, world_state) -> dict | None:
        """Return sensor data if drone is inside boundary polygon, None otherwise."""
        if self.boundary_polygon is None:
            return None

        telemetry = world_state.get_drone_telemetry(drone_id)
        if telemetry is None:
            return None

        if not point_in_polygon(telemetry.lat, telemetry.lon, self.boundary_polygon):
            return None

        if self.disaster_type == "fire":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.3,
                "hazard_flags": ["active_fire", "smoke"],
                "visibility_m": 200.0,
                "wind_speed": 12.0,
            }
        elif self.disaster_type == "structural_collapse":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.6,
                "hazard_flags": ["unstable_structure"],
                "visibility_m": 5000.0,
                "wind_speed": 5.0,
            }
        elif self.disaster_type == "flood":
            return {
                "thermal_detected": False,
                "survivor_probability": 0.4,
                "hazard_flags": ["rising_water"],
                "visibility_m": 3000.0,
                "wind_speed": 8.0,
            }
        elif self.disaster_type == "industrial_hazard":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.1,
                "hazard_flags": ["toxic_gas", "explosion_risk"],
                "visibility_m": 500.0,
                "wind_speed": 6.0,
            }
        elif self.disaster_type == "maritime_sar":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.5,
                "hazard_flags": ["rough_seas"],
                "visibility_m": 8000.0,
                "wind_speed": 20.0,
            }

        return {
            "thermal_detected": False,
            "survivor_probability": 0.0,
            "hazard_flags": [],
            "visibility_m": 10000.0,
            "wind_speed": 5.0,
        }
