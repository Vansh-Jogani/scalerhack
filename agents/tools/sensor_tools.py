"""Sensor tools for agent data collection."""


GET_SENSOR_READING_TOOL = {
    "name": "get_sensor_reading",
    "description": "Get sensor data at the drone's current position. Returns sensor readings if the drone is over an active incident area, or null if outside any incident zone.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drone_id": {"type": "string", "description": "ID of the drone to read sensors from"},
        },
        "required": ["drone_id"],
    },
}


def create_get_sensor_reading_handler(sensor_overlay, world_state):
    async def get_sensor_reading(drone_id: str) -> dict:
        reading = sensor_overlay.get_reading(drone_id, world_state)
        if reading is None:
            return {"status": "no_data", "message": "No sensor data at current position"}
        return {"status": "ok", "data": reading}
    return get_sensor_reading
