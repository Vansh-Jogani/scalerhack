import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from sim.world_state import WorldState
from sim.sensor_overlay import SensorOverlay
from orchestrator.orchestrator import ARIAOrchestrator
from agents.agent1_surveillance import SurveillanceAgent

load_dotenv()
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger()

config_path = Path("config.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

world_state: WorldState | None = None
sensor_overlay: SensorOverlay | None = None
orchestrator: ARIAOrchestrator | None = None
active_agent1: SurveillanceAgent | None = None
connected_clients: list[WebSocket] = []


async def broadcast_event(event_type: str, data: dict) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    msg = {"type": event_type, "data": data}
    for ws in list(connected_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            if ws in connected_clients:
                connected_clients.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global world_state, sensor_overlay, orchestrator
    scenario_path = Path(config["simulation"]["scenario"])
    world_state = WorldState(scenario_path)
    sensor_overlay = SensorOverlay()
    orchestrator = ARIAOrchestrator(
        world_state,
        sensor_overlay,
        model=config["models"]["agent1"],
        agent3_endpoint=config["models"]["agent3_endpoint"],
        agent3_model=config["models"]["agent3_model"],
    )
    orchestrator.set_event_callback(broadcast_event)

    world_state.add_drone(
        "drone-001", "fixed_wing",
        world_state.home_position["lat"],
        world_state.home_position["lon"],
    )
    tick_rate = config["simulation"]["tick_rate_hz"]
    tick_task = asyncio.create_task(tick_loop(tick_rate))
    broadcast_task = asyncio.create_task(broadcast_loop())
    logger.info("system_started", scenario=str(scenario_path), tick_rate=tick_rate)
    yield
    tick_task.cancel()
    broadcast_task.cancel()


async def tick_loop(tick_rate_hz: int):
    dt = 1.0 / tick_rate_hz
    while True:
        world_state.tick(dt)
        await asyncio.sleep(dt)


async def broadcast_loop():
    while True:
        if connected_clients and world_state:
            telemetry = world_state.get_all_telemetry()
            markers = [m.model_dump() for m in world_state.get_markers()]
            for ws in list(connected_clients):
                try:
                    for t in telemetry:
                        await ws.send_json({"type": "telemetry", "data": t})
                    await ws.send_json({"type": "markers", "data": markers})
                except Exception:
                    if ws in connected_clients:
                        connected_clients.remove(ws)
        await asyncio.sleep(0.1)


async def world_event_task(delay: int = 30):
    """Fire a world event after delay seconds — grows the first marker's radius."""
    await asyncio.sleep(delay)
    if world_state and world_state.markers:
        m = world_state.markers[0]
        m.radius_m += 50.0
        event = {"type": "fire_growth", "marker_id": m.id, "new_radius_m": m.radius_m}
        logger.info("world_event_fired", **event)
        await orchestrator.trigger_world_event(event)


app = FastAPI(title="ARIA v1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("ws_connected", client=str(websocket.client))
    await websocket.send_json({"type": "hello", "status": "connected", "drones": len(world_state.drones), "markers": len(world_state.markers)})
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "command":
                action = msg.get("action")
                if action == "fly_to":
                    payload = msg["data"]
                    world_state.command_drone(payload["drone_id"], payload["lat"], payload["lon"], payload["alt"])
                    await websocket.send_json({"type": "ack", "action": "fly_to", "status": "ok"})
                elif action == "go":
                    agent1_payload = await orchestrator.receive_go_signal(msg["data"])
                    await websocket.send_json({
                        "type": "ack", "action": "go", "status": "ok",
                        "agent1_payload": agent1_payload,
                    })
                    asyncio.create_task(world_event_task(delay=30))
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info("ws_disconnected")


if __name__ == "__main__":
    uvicorn.run("main:app", host=config["server"]["host"], port=config["server"]["port"], reload=False)
