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
from pydantic import BaseModel

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


async def broadcast_event(event_type: str, data: dict) -> None:
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
        model_a1=config["models"]["agent1"],
        model_a2=config["models"]["agent2"],
        model_a3=config["models"]["agent3"],
    )
    orchestrator.set_event_callback(broadcast_event)

    world_state.add_drone(
        "drone-001", "fixed_wing",
        world_state.home_position["lat"],
        world_state.home_position["lon"],
    )

    tick_rate = config["simulation"]["tick_rate_hz"]

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        async with AsyncSqliteSaver.from_conn_string("aria_checkpoints.db") as checkpointer:
            orchestrator.setup_graph(checkpointer)
            tick_task = asyncio.create_task(tick_loop(tick_rate))
            broadcast_task = asyncio.create_task(broadcast_loop())
            logger.info("system_started", scenario=str(scenario_path), langgraph=True)
            yield
            tick_task.cancel()
            broadcast_task.cancel()
    except ImportError:
        logger.warning("langgraph_not_installed", detail="running without LangGraph checkpointing")
        tick_task = asyncio.create_task(tick_loop(tick_rate))
        broadcast_task = asyncio.create_task(broadcast_loop())
        logger.info("system_started", scenario=str(scenario_path), langgraph=False)
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
            zones = world_state.get_zones()
            survivors = world_state.get_survivor_markers()
            markers = [m.model_dump() for m in world_state.get_markers()]
            bases = world_state.get_bases()
            for ws in list(connected_clients):
                try:
                    for t in telemetry:
                        await ws.send_json({"type": "telemetry", "data": t})
                    await ws.send_json({"type": "markers", "data": markers})
                    await ws.send_json({"type": "bases", "data": bases})
                    if zones:
                        await ws.send_json({"type": "zones", "data": zones})
                    if survivors:
                        await ws.send_json({"type": "survivors", "data": survivors})
                except Exception:
                    if ws in connected_clients:
                        connected_clients.remove(ws)
        await asyncio.sleep(0.1)


async def world_event_task(delay: int = 30):
    await asyncio.sleep(delay)
    if world_state and world_state.markers:
        m = world_state.markers[0]
        m.radius_m += 50.0
        event = {"type": "fire_growth", "marker_id": m.id, "new_radius_m": m.radius_m}
        logger.info("world_event_fired", **event)
        await orchestrator.trigger_world_event(event)


app = FastAPI(title="ARIA v1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
async def health():
    return {"status": "ok"}


class IncidentPayload(BaseModel):
    lat: float = 0.0
    lon: float = 0.0
    area: dict | None = None
    disaster_type: str = "fire"
    type: str | None = None
    severity: str = "medium"
    zone_radius_m: float | None = None
    zone_polygon: list | None = None


@app.post("/api/incident/create")
async def create_incident(payload: IncidentPayload):
    disaster_type = payload.type or payload.disaster_type
    if payload.area and "center" in payload.area:
        area = payload.area
    else:
        lat = payload.area.get("lat", payload.lat) if payload.area else payload.lat
        lon = payload.area.get("lon", payload.lon) if payload.area else payload.lon
        area = {
            "center": {"lat": lat, "lon": lon},
            "radius_m": payload.zone_radius_m or 600.0,
        }
    go_payload = {"area": area, "disaster_type": disaster_type, "severity": payload.severity}
    agent1_payload = await orchestrator.receive_go_signal(go_payload)
    asyncio.create_task(world_event_task(delay=30))
    return {
        "status": "ok",
        "incident_id": agent1_payload.get("incident_id"),
        "agent1_payload": agent1_payload,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("ws_connected", client=str(websocket.client))
    await websocket.send_json({
        "type": "hello",
        "status": "connected",
        "drones": len(world_state.drones),
        "markers": len(world_state.markers),
        "bases": world_state.get_bases(),
    })
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "command":
                action = msg.get("action")
                if action == "fly_to":
                    p = msg["data"]
                    world_state.command_drone(p["drone_id"], p["lat"], p["lon"], p["alt"])
                    await websocket.send_json({"type": "ack", "action": "fly_to", "status": "ok"})
                elif action == "go":
                    agent1_payload = await orchestrator.receive_go_signal(msg["data"])
                    await websocket.send_json({
                        "type": "ack",
                        "action": "go",
                        "status": "ok",
                        "agent1_payload": agent1_payload,
                    })
                    asyncio.create_task(world_event_task(delay=30))
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info("ws_disconnected")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config["server"]["host"],
        port=config["server"]["port"],
        reload=False,
    )
