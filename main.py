import asyncio
import json
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from sim_layer.tracer import tracer

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

_rc_path = Path("frontend/src/data/response_centres.json")
response_centres: list = json.loads(_rc_path.read_text()) if _rc_path.exists() else []

world_state: WorldState | None = None
sensor_overlay: SensorOverlay | None = None
orchestrator: ARIAOrchestrator | None = None
connected_clients: list[WebSocket] = []

MAX_WS_CONNECTIONS = 20


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
        model_a4=config["models"].get("agent4", config["models"]["agent3"]),
        response_centres=response_centres,
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
            markers = [m.model_dump() for m in world_state.get_markers()]
            zones = world_state.get_zones()
            survivors = world_state.get_survivor_markers()
            bases = world_state.get_bases()

            frame = {
                "type": "frame",
                "data": {
                    "telemetry": telemetry,
                    "markers": markers,
                    "bases": bases,
                    "zones": zones if zones else [],
                    "survivors": survivors if survivors else [],
                },
            }
            for ws in list(connected_clients):
                try:
                    await ws.send_json(frame)
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
    if len(connected_clients) >= MAX_WS_CONNECTIONS:
        await websocket.close(code=4003, reason="max connections reached")
        return
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


# ── Webhook endpoint — external event ingress ──────────────────────────────────

class WebhookAlert(BaseModel):
    source: str
    alert_type: str
    lat: float
    lon: float
    severity: str = "medium"
    description: str = ""
    timestamp: str | None = None


def _haversine_distance(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.post("/api/webhook/alert")
async def receive_webhook_alert(alert: WebhookAlert):
    """External event ingress — accepts IoT sensor alerts, citizen reports, weather warnings."""
    ts = alert.timestamp or datetime.now(timezone.utc).isoformat()
    logger.info(
        "webhook_received",
        source=alert.source,
        alert_type=alert.alert_type,
        lat=alert.lat,
        lon=alert.lon,
        severity=alert.severity,
    )
    tracer.trace_webhook(alert.source, alert.alert_type, {"lat": alert.lat, "lon": alert.lon, "severity": alert.severity})

    await broadcast_event("webhook_received", {
        "source": alert.source,
        "alert_type": alert.alert_type,
        "lat": alert.lat,
        "lon": alert.lon,
        "severity": alert.severity,
        "description": alert.description,
        "timestamp": ts,
    })

    # Check if this alert is near an existing active marker
    near_existing = False
    for marker in world_state.get_markers():
        dist = _haversine_distance(alert.lat, alert.lon, marker.lat, marker.lon)
        if dist < (marker.radius_m + 200):
            near_existing = True
            logger.info("webhook_near_existing", marker_id=marker.id, distance_m=dist)
            if orchestrator:
                event = {
                    "type": "external_alert",
                    "source": alert.source,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "description": alert.description,
                    "near_marker": marker.id,
                }
                await orchestrator.trigger_world_event(event)
            break

    if not near_existing:
        # New location — create a new incident
        disaster_map = {
            "smoke_detected": "fire",
            "fire_alarm": "fire",
            "flood_warning": "flood",
            "gas_leak": "industrial_hazard",
            "structural_alert": "structural_collapse",
            "person_in_water": "maritime_sar",
        }
        disaster_type = disaster_map.get(alert.alert_type, "fire")
        go_payload = {
            "area": {"center": {"lat": alert.lat, "lon": alert.lon}, "radius_m": 600.0},
            "disaster_type": disaster_type,
            "severity": alert.severity,
        }
        agent1_payload = await orchestrator.receive_go_signal(go_payload)
        asyncio.create_task(world_event_task(delay=30))
        logger.info("webhook_new_incident", incident_id=agent1_payload.get("incident_id"))
        return {
            "status": "new_incident_created",
            "incident_id": agent1_payload.get("incident_id"),
            "source": alert.source,
            "timestamp": ts,
        }

    return {
        "status": "existing_incident_updated",
        "source": alert.source,
        "timestamp": ts,
    }


# ── Pipeline status endpoint ───────────────────────────────────────────────────

@app.get("/api/pipeline/status")
async def pipeline_status():
    """Returns current orchestrator state, active incidents, and agent statuses."""
    state = "unknown"
    incidents = []
    if orchestrator:
        state = getattr(orchestrator, "current_state", "STANDBY")
        if hasattr(orchestrator, "incident_manager") and orchestrator.incident_manager:
            im = orchestrator.incident_manager
            for mid, incident in getattr(im, "active_incidents", {}).items():
                incidents.append({
                    "marker_id": mid,
                    "status": getattr(incident, "status", "active"),
                })
            for queued in getattr(im, "incident_queue", []):
                incidents.append({
                    "marker_id": getattr(queued, "id", "unknown"),
                    "status": "queued",
                })

    return {
        "orchestrator_state": state,
        "active_incidents": incidents,
        "connected_clients": len(connected_clients),
        "drones": len(world_state.drones) if world_state else 0,
        "markers": len(world_state.get_markers()) if world_state else 0,
        "uptime_s": None,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config["server"]["host"],
        port=config["server"]["port"],
        reload=False,
    )
