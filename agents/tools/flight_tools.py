"""Flight tools for agent drone control."""

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


def create_fly_to_handler(world_state):
    async def fly_to(drone_id: str, lat: float, lon: float, alt: float) -> dict:
        success = world_state.command_drone(drone_id, lat, lon, alt)
        if success:
            return {"status": "ok", "message": f"Drone {drone_id} commanded to fly to ({lat}, {lon}, {alt}m)"}
        return {"status": "error", "message": f"Drone {drone_id} not found"}
    return fly_to
