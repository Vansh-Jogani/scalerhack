"""ARIA v1 — main entry point.

Starts FastAPI server, world state tick loop, WebSocket broadcast,
orchestrator, and all agent infrastructure.
"""

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
heartbeat_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------

async def broadcast_event(event_type: str, data: dict) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    msg = {"type": event_type, "data": data}
    for ws in list(connected_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            if ws in connected_clients:
                connected_clients.remove(ws)


# ---------------------------------------------------------------------------
# Background loops
# ---------------------------------------------------------------------------

async def tick_loop(tick_rate_hz: int):
    """Simulation tick loop — advances all drones."""
    dt = 1.0 / tick_rate_hz
    while True:
        world_state.tick(dt)
        await asyncio.sleep(dt)


async def broadcast_loop():
    """Broadcast telemetry and markers to all connected WS clients at ~10Hz."""
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


async def heartbeat_loop():
    """Agent 3 heartbeat — fires advisory update every 60 seconds.

    Per SPEC.md AGENT_3_CONFIG trigger: 60s_heartbeat_check
    """
    from agents.agent3_advisory import AdvisoryAgent

    while True:
        await asyncio.sleep(60)
        if orchestrator and orchestrator.agent1_report:
            logger.info("heartbeat_trigger", trigger="60s_heartbeat_check")
            agent3 = AdvisoryAgent(
                agent_id="agent-3",
                model=config["models"]["agent3"],
                orchestrator=orchestrator,
                stream_callback=broadcast_event,
            )
            try:
                advisory = await agent3.on_trigger(
                    trigger_type="60s_heartbeat_check",
                    agent1_report=orchestrator.agent1_report,
                    agent2_report=orchestrator.agent2_report or {},
                )
                await broadcast_event("advisory", advisory)
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))


async def world_event_task(delay: int = 90):
    """Schedule world event after GO signal.

    Per SPEC.md: For fire scenario, after 90 seconds fire grows by 20% radius,
    wind shifts 15°.
    """
    if world_state and world_state.markers:
        marker = world_state.markers[0]
        await world_state.schedule_event(
            event_type="fire_growth",
            delay_seconds=delay,
            marker_id=marker.id,
            orchestrator=orchestrator,
        )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global world_state, sensor_overlay, orchestrator, heartbeat_task

    scenario_path = Path(config["simulation"]["scenario"])
    world_state = WorldState(scenario_path)
    sensor_overlay = SensorOverlay()
    orchestrator = ARIAOrchestrator(
        world_state,
        sensor_overlay,
        model=config["models"]["agent1"],
        agent3_model=config["models"]["agent3"],
    )
    orchestrator.set_event_callback(broadcast_event)

    # Spawn initial surveillance drone
    world_state.add_drone(
        "drone-001", "fixed_wing",
        world_state.home_position["lat"],
        world_state.home_position["lon"],
    )

    tick_rate = config["simulation"]["tick_rate_hz"]
    tick_task = asyncio.create_task(tick_loop(tick_rate))
    bcast_task = asyncio.create_task(broadcast_loop())
    heartbeat_task = asyncio.create_task(heartbeat_loop())

    logger.info("system_started", scenario=str(scenario_path), tick_rate=tick_rate)
    yield
    tick_task.cancel()
    bcast_task.cancel()
    heartbeat_task.cancel()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="ARIA v1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# REST API — /api/incident/create (for AdminPanel)
# ---------------------------------------------------------------------------

class IncidentCreateRequest(BaseModel):
    area: dict
    disaster_type: str = "fire"


@app.post("/api/incident/create")
async def create_incident(request: IncidentCreateRequest):
    """Create a new incident from the admin panel.

    This is the entry point for the GO signal when triggered via REST
    instead of WebSocket.
    """
    payload = {
        "area": request.area,
        "disaster_type": request.disaster_type,
    }
    agent1_payload = await orchestrator.receive_go_signal(payload)

    # Schedule world event (fire growth after 90 seconds)
    asyncio.create_task(world_event_task(delay=90))

    return {
        "status": "ok",
        "agent1_payload": agent1_payload,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Legacy WebSocket endpoint — telemetry + commands."""
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
                    agent1_payload = await orchestrator.receive_go_signal(msg["data"])
                    await websocket.send_json({
                        "type": "ack", "action": "go", "status": "ok",
                        "agent1_payload": agent1_payload,
                    })
                    asyncio.create_task(world_event_task(delay=90))
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info("ws_disconnected")


if __name__ == "__main__":
    uvicorn.run("main:app", host=config["server"]["host"], port=config["server"]["port"], reload=True)
