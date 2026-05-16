"""World state: markers, drones, zones, survivors, hazards, tick loop."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set

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
    # Hybrid discovery fields — ground_truth_type hidden from agents
    type_hint: Optional[str] = None
    ground_truth_type: Optional[str] = None

    @property
    def operator_hint(self) -> str:
        return self.type_hint or self.type

    @property
    def truth(self) -> str:
        return self.ground_truth_type or self.type


# Pre-distributed deployment bases across Hyderabad demo area
DEPLOYMENT_BASES = [
    {"id": "base-alpha",  "name": "Alpha Base",  "lat": 17.3920, "lon": 78.4840, "stocked_drone_types": ["fixed_wing", "rotary", "micro_rotary"]},
    {"id": "base-bravo",  "name": "Bravo Base",  "lat": 17.3800, "lon": 78.4920, "stocked_drone_types": ["rotary", "micro_rotary"]},
    {"id": "base-charlie","name": "Charlie Base", "lat": 17.3860, "lon": 78.5010, "stocked_drone_types": ["fixed_wing", "rotary"]},
    {"id": "base-delta",  "name": "Delta Base",  "lat": 17.3760, "lon": 78.4830, "stocked_drone_types": ["rotary", "micro_rotary"]},
    {"id": "base-echo",   "name": "Echo Base",   "lat": 17.3940, "lon": 78.4960, "stocked_drone_types": ["fixed_wing", "rotary"]},
]


class WorldState:
    def __init__(self, scenario_path: Optional[Path] = None) -> None:
        self.markers: List[Marker] = []
        self.drones: Dict[str, DroneModel] = {}
        self.zones: List[dict] = []
        self.survivor_markers: List[dict] = []
        self.hazard_markers: List[dict] = []
        self.tick_count: int = 0
        self.home_position: Dict[str, float] = {"lat": 0.0, "lon": 0.0, "alt": 0.0}
        self._running: bool = False
        self.bases: List[dict] = list(DEPLOYMENT_BASES)
        self._swarm_leaders: Set[str] = set()  # drone_ids tagged as swarm leader
        self.boundary_polygon: Optional[List] = None
        self.scenario_center: Optional[Dict[str, float]] = None

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
        self.boundary_polygon = data.get("boundary_polygon")
        center = data.get("center")
        if center:
            self.scenario_center = {"lat": center["lat"], "lon": center["lon"]}

    # ── Markers ──────────────────────────────────────────────────────────

    def add_marker(self, marker: "Marker") -> None:
        self.markers = [m for m in self.markers if m.id != marker.id]
        self.markers.append(marker)

    def get_markers(self) -> List[Marker]:
        return self.markers

    # ── Drones ───────────────────────────────────────────────────────────

    def get_drone_telemetry(self, drone_id: Optional[str] = None):
        if drone_id is not None:
            drone = self.drones.get(drone_id)
            return drone.get_telemetry() if drone else None
        return {did: drone.get_telemetry() for did, drone in self.drones.items()}

    def get_all_telemetry(self) -> List[dict]:
        result = []
        for drone in self.drones.values():
            t = drone.get_telemetry().__dict__.copy()
            t["swarm_leader"] = drone.drone_id in self._swarm_leaders
            t["drone_type"] = drone.drone_type
            result.append(t)
        return result

    def get_bases(self) -> List[dict]:
        return list(self.bases)

    def mark_swarm_leader(self, drone_id: str) -> None:
        self._swarm_leaders.add(drone_id)

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

    def reposition_drone(self, drone_id: str, lat: float, lon: float, alt: float = 0.0) -> bool:
        """Teleport a drone to a new position and update its home (for RTL)."""
        if drone_id not in self.drones:
            return False
        drone = self.drones[drone_id]
        drone.lat = lat
        drone.lon = lon
        drone.alt = alt
        drone.home_lat = lat
        drone.home_lon = lon
        drone.home_alt = alt
        return True

    def command_drone(self, drone_id: str, lat: float, lon: float, alt: float) -> bool:
        if drone_id not in self.drones:
            return False
        self.drones[drone_id].set_target(lat, lon, alt)
        return True

    # ── Zones ─────────────────────────────────────────────────────────────

    def add_zone(self, zone: dict) -> None:
        """Add or update a zone (identified by zone.id)."""
        zone_id = zone.get("id") or zone.get("zone_id")
        if zone_id:
            self.zones = [z for z in self.zones if z.get("id") != zone_id]
        self.zones.append(zone)

    def get_zones(self) -> List[dict]:
        return list(self.zones)

    # ── Survivors ─────────────────────────────────────────────────────────

    def add_survivor(self, survivor: dict) -> None:
        """Add or update a survivor marker (identified by survivor.id)."""
        sid = survivor.get("id")
        if sid:
            self.survivor_markers = [s for s in self.survivor_markers if s.get("id") != sid]
        self.survivor_markers.append(survivor)

    def get_survivor_markers(self) -> List[dict]:
        return list(self.survivor_markers)

    # ── Hazards ───────────────────────────────────────────────────────────

    def add_hazard(self, hazard: dict) -> None:
        hid = hazard.get("id")
        if hid:
            self.hazard_markers = [h for h in self.hazard_markers if h.get("id") != hid]
        self.hazard_markers.append(hazard)

    def get_hazard_markers(self) -> List[dict]:
        return list(self.hazard_markers)

    # ── Tick loop ─────────────────────────────────────────────────────────

    def stop_tick_loop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # World event simulation (Stage 4)
    # ------------------------------------------------------------------

    async def schedule_event(
        self,
        event_type: str,
        delay_seconds: float,
        marker_id: str,
        orchestrator=None,
    ) -> None:
        """Schedule a world event to fire after a delay.

        For fire scenario: after delay, fire grows by 20% radius, wind shifts 15°.
        This fires the 'world_event_fired' trigger to Agent 3 via orchestrator.
        """
        await asyncio.sleep(delay_seconds)

        marker = next((m for m in self.markers if m.id == marker_id), None)
        if marker is None:
            return

        event = {"type": event_type, "marker_id": marker_id}

        if event_type == "fire_growth":
            old_radius = marker.radius_m
            marker.radius_m *= 1.2  # 20% growth
            event["old_radius_m"] = old_radius
            event["new_radius_m"] = marker.radius_m
            event["wind_shift_deg"] = 15.0
            event["description"] = (
                f"Fire area grew from {old_radius:.0f}m to {marker.radius_m:.0f}m radius. "
                f"Wind shifted 15° clockwise."
            )
        elif event_type == "aftershock":
            event["description"] = "Aftershock detected — structural reassessment required."
        elif event_type == "flood_surge":
            marker.radius_m *= 1.3
            event["description"] = "Flood surge — water level rising."
        else:
            event["description"] = f"World event: {event_type}"

        if orchestrator:
            await orchestrator.trigger_world_event(event)
