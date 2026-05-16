"""Synthetic sensor returns based on drone position vs incident boundary polygon."""

import random
from sim.drone_model import _haversine_distance


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
        """Return sensor data if drone is near the incident, None otherwise."""
        if not self.disaster_type:
            return None

        telemetry = world_state.get_drone_telemetry(drone_id)
        if telemetry is None:
            return None

        # Find the primary active marker for the current disaster type
        active_marker = next((m for m in world_state.get_markers() if m.type == self.disaster_type), None)
        
        if active_marker:
            c_lat, c_lon = active_marker.lat, active_marker.lon
            radius = active_marker.radius_m
        elif self.boundary_polygon:
            c_lat = sum(p[0] for p in self.boundary_polygon) / len(self.boundary_polygon)
            c_lon = sum(p[1] for p in self.boundary_polygon) / len(self.boundary_polygon)
            radius = 500.0 # fallback radius
        else:
            return None

        dist = _haversine_distance(telemetry.lat, telemetry.lon, c_lat, c_lon)
        
        # Only return readings if within the effective radius (or slightly outside for edge cases)
        if dist > radius * 1.5:
            return None
        
        # Distance falloff multiplier (1.0 at center, drops to 0 at the edge of the effective radius)
        falloff = max(0.0, 1.0 - (dist / (radius * 1.5)))
        
        # Wind model with noise jitter and relative direction
        world_wind = world_state.get_wind()
        wind_speed_noisy = max(0.0, world_wind.get("speed_ms", 5.0) + random.gauss(0, 1.0))
        rel_wind_bearing = (world_wind.get("bearing_deg", 0) - telemetry.heading) % 360

        if self.disaster_type == "fire":
            # Altitude degradation: thermal drops above 80m
            thermal = True if telemetry.alt <= 80.0 else False
            return {
                "thermal_detected": thermal,
                "survivor_probability": 0.3 * falloff,
                "hazard_flags": ["active_fire", "smoke"],
                "visibility_m": 200.0 + (dist * 0.5), # Visibility improves further away from smoke center
                "wind_speed": wind_speed_noisy,
                "wind_direction_relative": rel_wind_bearing,
            }
        elif self.disaster_type == "structural_collapse":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.6 * falloff,
                "hazard_flags": ["unstable_structure"],
                "visibility_m": 5000.0,
                "wind_speed": wind_speed_noisy,
                "wind_direction_relative": rel_wind_bearing,
            }
        elif self.disaster_type == "flood":
            return {
                "thermal_detected": False,
                "survivor_probability": 0.4 * falloff,
                "hazard_flags": ["rising_water"],
                "visibility_m": 3000.0,
                "wind_speed": wind_speed_noisy,
                "wind_direction_relative": rel_wind_bearing,
            }
        elif self.disaster_type == "industrial_hazard":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.1 * falloff,
                "hazard_flags": ["toxic_gas", "explosion_risk"],
                "visibility_m": 500.0 + (dist * 0.2),
                "wind_speed": wind_speed_noisy,
                "wind_direction_relative": rel_wind_bearing,
            }
        elif self.disaster_type == "maritime_sar":
            return {
                "thermal_detected": True,
                "survivor_probability": 0.5 * falloff,
                "hazard_flags": ["rough_seas"],
                "visibility_m": 8000.0,
                "wind_speed": wind_speed_noisy,
                "wind_direction_relative": rel_wind_bearing,
            }

        return {
            "thermal_detected": False,
            "survivor_probability": 0.0,
            "hazard_flags": [],
            "visibility_m": 10000.0,
            "wind_speed": wind_speed_noisy,
            "wind_direction_relative": rel_wind_bearing,
        }
