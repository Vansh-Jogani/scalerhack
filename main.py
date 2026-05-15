import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import structlog
import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

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
connected_clients: list[WebSocket] = []

_db_conn = None
_checkpointer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global world_state, sensor_overlay, orchestrator, _db_conn, _checkpointer

    scenario_path = Path(config["simulation"]["scenario"])
    world_state = WorldState(scenario_path)
    sensor_overlay = SensorOverlay()

    orchestrator = ARIAOrchestrator(
        world_state,
        sensor_overlay,
        agent1_model=config["models"]["agent1"],
        agent2_model=config["models"]["agent2"],
        agent3_model=config["models"]["agent3"],
    )
    orchestrator.set_broadcast(broadcast)

    # Wire Agent 1 (single fixed-wing recon drone, starts at home)
    world_state.add_drone(
        "drone-001", "fixed_wing",
        world_state.home_position["lat"],
        world_state.home_position["lon"],
    )
    agent1 = SurveillanceAgent(
        "agent1",
        config["models"]["agent1"],
        world_state, sensor_overlay, orchestrator,
        "drone-001",
    )
    agent1.set_broadcast(broadcast)
    orchestrator.agent1 = agent1

    # LangGraph SQLite checkpointer
    _db_conn = await aiosqlite.connect("aria_checkpoints.db")
    _checkpointer = AsyncSqliteSaver(_db_conn)
    await orchestrator.setup_graph(_checkpointer)

    tick_rate = config["simulation"]["tick_rate_hz"]
    tick_task = asyncio.create_task(tick_loop(tick_rate))
    broadcast_task = asyncio.create_task(broadcast_loop())

    logger.info("aria_started", scenario=str(scenario_path), tick_rate=tick_rate)
    yield

    tick_task.cancel()
    broadcast_task.cancel()
    if _db_conn:
        await _db_conn.close()


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
            zones = world_state.get_zone_list()
            survivors = world_state.get_survivor_list()

            for ws in list(connected_clients):
                try:
                    for t in telemetry:
                        await ws.send_json({"type": "telemetry", "data": t})
                    await ws.send_json({"type": "markers", "data": markers})
                    if zones:
                        await ws.send_json({"type": "zones", "data": zones})
                    if survivors:
                        await ws.send_json({"type": "survivors", "data": survivors})
                except Exception:
                    try:
                        connected_clients.remove(ws)
                    except ValueError:
                        pass
        await asyncio.sleep(0.1)


async def broadcast(msg: dict):
    """Broadcast a message to all connected WebSocket clients."""
    for ws in list(connected_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            try:
                connected_clients.remove(ws)
            except ValueError:
                pass


app = FastAPI(title="ARIA v1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/state")
async def get_state():
    return {
        "state": orchestrator.state if orchestrator else "STANDBY",
        "incident": orchestrator.active_incident if orchestrator else None,
        "advisory": orchestrator.agent3.latest_advisory if (orchestrator and orchestrator.agent3) else None,
    }


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
                if action == "go":
                    result = orchestrator.receive_go_signal(msg["data"])
                    await websocket.send_json({
                        "type": "ack", "action": "go", "status": "ok",
                        "incident_id": result.get("incident_id"),
                    })
                elif action == "fly_to":
                    payload = msg["data"]
                    world_state.command_drone(payload["drone_id"], payload["lat"], payload["lon"], payload["alt"])
                    await websocket.send_json({"type": "ack", "action": "fly_to", "status": "ok"})
    except WebSocketDisconnect:
        try:
            connected_clients.remove(websocket)
        except ValueError:
            pass
        logger.info("ws_disconnected")


if __name__ == "__main__":
    uvicorn.run("main:app", host=config["server"]["host"], port=config["server"]["port"], reload=True)
