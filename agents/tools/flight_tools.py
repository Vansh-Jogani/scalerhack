"""Flight tools for agent drone control.

Tools: fly_to, loiter_over, rtl, abort
Per SPEC.md SHARED_TO_SIMULATION.drone_commands
"""

import time

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

LOITER_OVER_TOOL = {
    "name": "loiter_over",
    "description": "Command a drone to loiter (circle) over a position at a given radius for a specified duration.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drone_id": {"type": "string", "description": "ID of the drone to command"},
            "lat": {"type": "number", "description": "Center latitude of loiter pattern"},
            "lon": {"type": "number", "description": "Center longitude of loiter pattern"},
            "radius": {"type": "number", "description": "Loiter radius in meters"},
            "duration": {"type": "number", "description": "Loiter duration in seconds"},
        },
        "required": ["drone_id", "lat", "lon", "radius", "duration"],
    },
}

RTL_TOOL = {
    "name": "rtl",
    "description": "Command a drone to return to launch position immediately.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drone_id": {"type": "string", "description": "ID of the drone to return"},
        },
        "required": ["drone_id"],
    },
}

ABORT_TOOL = {
    "name": "abort",
    "description": "Immediately stop a drone — highest priority command. Use only in emergencies.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drone_id": {"type": "string", "description": "ID of the drone to abort"},
        },
        "required": ["drone_id"],
    },
}


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


def create_loiter_over_handler(world_state):
    """Create loiter_over tool handler bound to a WorldState instance."""
    async def loiter_over(drone_id: str, lat: float, lon: float, radius: float, duration: float) -> dict:
        drone = world_state.drones.get(drone_id)
        if drone is None:
            return {"status": "error", "message": f"Drone {drone_id} not found"}

        # Command drone to the loiter center first
        world_state.command_drone(drone_id, lat, lon, drone.alt)
        # Set loiter parameters on the drone
        drone.loiter_radius = radius
        drone.loiter_duration = duration
        loiter_start = time.time()

        return {
            "status": "ok",
            "drone_id": drone_id,
            "loiter_start": loiter_start,
            "expected_end": loiter_start + duration,
            "message": f"Drone {drone_id} loitering over ({lat}, {lon}) r={radius}m for {duration}s",
        }
    return loiter_over


def create_rtl_handler(world_state):
    """Create rtl (return to launch) tool handler bound to a WorldState instance."""
    async def rtl(drone_id: str) -> dict:
        drone = world_state.drones.get(drone_id)
        if drone is None:
            return {"status": "error", "message": f"Drone {drone_id} not found"}
        drone.return_to_launch()
        return {
            "status": "ok",
            "drone_id": drone_id,
            "message": f"Drone {drone_id} returning to launch",
        }
    return rtl


def create_abort_handler(world_state):
    """Create abort tool handler bound to a WorldState instance."""
    async def abort(drone_id: str) -> dict:
        drone = world_state.drones.get(drone_id)
        if drone is None:
            return {"status": "error", "message": f"Drone {drone_id} not found"}
        # Immediate stop — clear target, set state to IDLE
        drone.target_lat = None
        drone.target_lon = None
        drone.target_alt = None
        drone.state = "IDLE"
        return {
            "status": "ok",
            "drone_id": drone_id,
            "message": f"Drone {drone_id} ABORTED — immediate stop",
        }
    return abort
