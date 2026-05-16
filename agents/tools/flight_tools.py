"""Flight tools for agent drone control.

Tools: fly_to, loiter_over, rtl, abort
Per SPEC.md SHARED_TO_SIMULATION.drone_commands
"""

import time

import math

FLY_TO_TOOL = {
    "name": "fly_to",
    "description": "Command a drone to fly to specified coordinates. The drone will begin moving toward the target at its cruise speed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drone_id": {"type": "string", "description": "ID of the drone to command"},
            "lat": {"type": "number", "description": "Target latitude"},
            "lon": {"type": "number", "description": "Target longitude"},
            "alt": {"type": "number", "description": "Target altitude in meters AGL"},
        },
        "required": ["drone_id", "lat", "lon", "alt"],
    },
}

FIND_NEAREST_BASE_TOOL = {
    "name": "find_nearest_base",
    "description": "Find the nearest deployment base that stocks the required drone type for your swarm. Returns base coordinates to launch from.",
    "input_schema": {
        "type": "object",
        "properties": {
            "swarm_type": {
                "type": "string",
                "enum": ["fixed_wing", "rotary", "micro_rotary"],
                "description": "Drone type required for this swarm mission",
            },
            "incident_lat": {"type": "number", "description": "Incident latitude (for distance calculation)"},
            "incident_lon": {"type": "number", "description": "Incident longitude (for distance calculation)"},
        },
        "required": ["swarm_type", "incident_lat", "incident_lon"],
    },
}

LAUNCH_FROM_BASE_TOOL = {
    "name": "launch_from_base",
    "description": "Spawn a swarm drone at a specific deployment base. The drone will appear at the base coordinates ready to fly.",
    "input_schema": {
        "type": "object",
        "properties": {
            "base_id": {"type": "string", "description": "Base ID returned by find_nearest_base"},
            "drone_id": {"type": "string", "description": "ID to assign to this drone"},
            "drone_type": {"type": "string", "enum": ["fixed_wing", "rotary", "micro_rotary"]},
        },
        "required": ["base_id", "drone_id", "drone_type"],
    },
}


def _haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def create_fly_to_handler(world_state):
    """Create fly_to tool handler bound to a WorldState instance."""
    async def fly_to(drone_id: str, lat: float, lon: float, alt: float) -> dict:
        success = world_state.command_drone(drone_id, lat, lon, alt)
        if success:
            return {
                "status": "ok",
                "drone_id": drone_id,
                "target_lat": lat,
                "target_lon": lon,
                "target_alt": alt,
                "message": f"Drone {drone_id} commanded to fly to ({lat}, {lon}, {alt}m)",
            }
        return {"status": "error", "message": f"Drone {drone_id} not found"}
    return fly_to


def create_find_nearest_base_handler(world_state):
    async def find_nearest_base(swarm_type: str, incident_lat: float, incident_lon: float) -> dict:
        candidates = [b for b in world_state.get_bases() if swarm_type in b["stocked_drone_types"]]
        if not candidates:
            candidates = world_state.get_bases()
        best = min(candidates, key=lambda b: _haversine(incident_lat, incident_lon, b["lat"], b["lon"]))
        dist_m = _haversine(incident_lat, incident_lon, best["lat"], best["lon"])
        return {
            "status": "ok",
            "base_id": best["id"],
            "name": best["name"],
            "lat": best["lat"],
            "lon": best["lon"],
            "distance_m": round(dist_m),
        }
    return find_nearest_base


def create_launch_from_base_handler(world_state):
    async def launch_from_base(base_id: str, drone_id: str, drone_type: str) -> dict:
        base = next((b for b in world_state.get_bases() if b["id"] == base_id), None)
        if not base:
            return {"status": "error", "message": f"Base {base_id} not found"}
        world_state.add_drone(drone_id, drone_type, base["lat"], base["lon"])
        return {"status": "ok", "drone_id": drone_id, "lat": base["lat"], "lon": base["lon"], "base": base["name"]}
    return launch_from_base
