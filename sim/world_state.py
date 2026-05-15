"""World state: holds markers, drones, and the simulation tick loop."""

import asyncio
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


class WorldState:
    """Central world state for the simulation.

    Holds markers loaded from a scenario JSON, manages drone instances,
    and runs the simulation tick loop.
    """

    def __init__(self, scenario_path: Optional[Path] = None) -> None:
        self.markers: List[Marker] = []
        self.drones: Dict[str, DroneModel] = {}
        self.tick_count: int = 0
        self.home_position: Dict[str, float] = {"lat": 0.0, "lon": 0.0, "alt": 0.0}
        self._running: bool = False

        if scenario_path:
            self.load_scenario(str(scenario_path))

    def load_scenario(self, path: str) -> None:
        """Load a scenario from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        self.markers = [Marker(**m) for m in data.get("markers", [])]

        home = data.get("home_position", {})
        self.home_position = {
            "lat": home.get("lat", 0.0),
            "lon": home.get("lon", 0.0),
            "alt": home.get("alt", 0.0),
        }

    def get_markers(self) -> List[Marker]:
        """Return all markers."""
        return self.markers

    def get_drone_telemetry(self, drone_id: Optional[str] = None):
        """Return telemetry for one drone (by id) or all drones (dict)."""
        if drone_id is not None:
            drone = self.drones.get(drone_id)
            return drone.get_telemetry() if drone else None
        return {
            did: drone.get_telemetry()
            for did, drone in self.drones.items()
        }

    def get_all_telemetry(self) -> List[dict]:
        """Return all drone telemetry as a list of dicts (for WS broadcast)."""
        return [drone.get_telemetry().__dict__ for drone in self.drones.values()]

    def tick(self, dt: float) -> None:
        """Advance all drones by dt seconds."""
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
        """Add a drone to the world at the given position (defaults to home)."""
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

    def command_drone(
        self, drone_id: str, lat: float, lon: float, alt: float
    ) -> bool:
        """Command a drone to fly to a target position. Returns True on success."""
        if drone_id not in self.drones:
            return False
        self.drones[drone_id].set_target(lat, lon, alt)
        return True

    async def start_tick_loop(self, tick_rate_hz: float = 10.0) -> None:
        """Run the simulation tick loop at the given rate.

        This coroutine runs indefinitely until cancelled or stop_tick_loop()
        is called.
        """
        dt = 1.0 / tick_rate_hz
        self._running = True

        while self._running:
            for drone in self.drones.values():
                drone.tick(dt)
            self.tick_count += 1
            await asyncio.sleep(dt)

    def stop_tick_loop(self) -> None:
        """Signal the tick loop to stop."""
        self._running = False
