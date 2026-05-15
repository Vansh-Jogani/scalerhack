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
connected_clients: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global world_state, sensor_overlay, orchestrator
    scenario_path = Path(config["simulation"]["scenario"])
    world_state = WorldState(scenario_path)
    sensor_overlay = SensorOverlay()
    orchestrator = ARIAOrchestrator(world_state, sensor_overlay)
    world_state.add_drone("drone-001", "fixed_wing", world_state.home_position["lat"], world_state.home_position["lon"])
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
                    connected_clients.remove(ws)
        await asyncio.sleep(0.1)


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
                    agent1_payload = orchestrator.receive_go_signal(msg["data"])
                    await websocket.send_json({"type": "ack", "action": "go", "status": "ok", "agent1_payload": agent1_payload})
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info("ws_disconnected")


if __name__ == "__main__":
    uvicorn.run("main:app", host=config["server"]["host"], port=config["server"]["port"], reload=True)
