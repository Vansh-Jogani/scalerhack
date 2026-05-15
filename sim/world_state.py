"""World state: holds markers, drones, zones, and the simulation tick loop."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

from sim.drone_model import DroneModel
from sim.drone_interface import Telemetry


class Marker(BaseModel):
    id: str
    lat: float
    lon: float
    type: str
    radius_m: float
    severity: str
    confirmed: bool


class ZoneData(BaseModel):
    zone_id: str
    lat: float
    lon: float
    risk_level: str
    actionable: bool
    findings: dict


class SurvivorMarker(BaseModel):
    lat: float
    lon: float
    confidence: float
    drone_id: str = ""


class HazardMarker(BaseModel):
    lat: float
    lon: float
    type: str
    exclusion_radius_m: float


class WorldState:
    """Central world state for the simulation."""

    def __init__(self, scenario_path: Optional[Path] = None) -> None:
        self.markers: List[Marker] = []
        self.drones: Dict[str, DroneModel] = {}
        self.zones: Dict[str, ZoneData] = {}
        self.survivor_markers: List[SurvivorMarker] = []
        self.hazard_markers: List[HazardMarker] = []
        self.tick_count: int = 0
        self.home_position: Dict[str, float] = {"lat": 0.0, "lon": 0.0, "alt": 0.0}
        self._running: bool = False

        if scenario_path:
            self.load_scenario(str(scenario_path))

    def load_scenario(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        self.markers = [Marker(**m) for m in data.get("markers", [])]

        home = data.get("home_position", {})
        self.home_position = {
            "lat": home.get("lat", 0.0),
            "lon": home.get("lon", 0.0),
            "alt": home.get("alt", 0.0),
        }

    def get_markers(self) -> List[Marker]:
        return self.markers

    def get_drone_telemetry(self, drone_id: Optional[str] = None):
        if drone_id is not None:
            drone = self.drones.get(drone_id)
            return drone.get_telemetry() if drone else None
        return {did: drone.get_telemetry() for did, drone in self.drones.items()}

    def get_all_telemetry(self) -> List[dict]:
        result = []
        for drone in self.drones.values():
            t = drone.get_telemetry()
            result.append({
                "drone_id": t.drone_id,
                "lat": t.lat,
                "lon": t.lon,
                "alt": t.alt,
                "heading": t.heading,
                "speed": t.speed,
                "state": t.state,
                "battery_pct": t.battery_pct,
            })
        return result

    def tick(self, dt: float) -> None:
        for drone in self.drones.values():
            drone.tick(dt)
        self.tick_count += 1

    def add_drone(
        self,
        drone_id: str,
        drone_type: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> DroneModel:
        start_lat = lat if lat is not None else self.home_position["lat"]
        start_lon = lon if lon is not None else self.home_position["lon"]
        drone = DroneModel(
            drone_id=drone_id,
            drone_type=drone_type,
            lat=start_lat,
            lon=start_lon,
            alt=self.home_position["alt"],
        )
        self.drones[drone_id] = drone
        return drone

    def command_drone(self, drone_id: str, lat: float, lon: float, alt: float) -> bool:
        if drone_id not in self.drones:
            return False
        self.drones[drone_id].set_target(lat, lon, alt)
        return True

    def update_zone(self, zone_data: dict) -> None:
        zone = ZoneData(
            zone_id=zone_data["zone_id"],
            lat=zone_data["lat"],
            lon=zone_data["lon"],
            risk_level=zone_data.get("risk_level", "low"),
            actionable=zone_data.get("actionable", False),
            findings=zone_data.get("findings", {}),
        )
        self.zones[zone.zone_id] = zone

    def add_survivor_marker(self, data: dict) -> None:
        self.survivor_markers.append(SurvivorMarker(
            lat=data["lat"],
            lon=data["lon"],
            confidence=data.get("confidence", 0.5),
            drone_id=data.get("drone_id", ""),
        ))

    def add_hazard_marker(self, data: dict) -> None:
        self.hazard_markers.append(HazardMarker(
            lat=data["lat"],
            lon=data["lon"],
            type=data.get("type", "unknown"),
            exclusion_radius_m=data.get("exclusion_radius_m", 50.0),
        ))

    def get_zone_list(self) -> List[dict]:
        return [z.model_dump() for z in self.zones.values()]

    def get_survivor_list(self) -> List[dict]:
        return [s.model_dump() for s in self.survivor_markers]

    def get_hazard_list(self) -> List[dict]:
        return [h.model_dump() for h in self.hazard_markers]
