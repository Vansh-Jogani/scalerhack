# ARIA v1 — Multi-Agent Drone Swarm Simulation

Autonomous drone swarm system for disaster response. Three AI agents (Claude + Ollama) control simulated drones, identify incidents, deploy specialist swarms, and produce response plans on a Mapbox operator screen.

## Quickstart

### 1. Setup (one time)

**Windows:**
```
setup.bat
```

**Linux/Mac:**
```bash
chmod +x setup.sh run.sh
./setup.sh
```

### 2. Configure API Keys

Edit `.env` in the project root:
```
ANTHROPIC_API_KEY=sk-ant-your_key_here
MAPBOX_TOKEN=pk.your_mapbox_token_here
VITE_MAPBOX_TOKEN=pk.your_mapbox_token_here
```

Edit `frontend/.env`:
```
VITE_MAPBOX_TOKEN=pk.your_mapbox_token_here
```

Get keys from:
- Anthropic: https://console.anthropic.com/
- Mapbox: https://account.mapbox.com/access-tokens/

### 3. Run

**Windows:**
```
run.bat
```

**Linux/Mac:**
```bash
./run.sh
```

Opens:
- Backend: http://localhost:8000/health
- Frontend: http://localhost:5173

## Architecture

```
Operator UI (Mapbox) ← WebSocket → FastAPI Backend
                                         │
                    ┌────────────────────┤
                    │                    │
              Orchestrator         World State
              (state machine)     (drones + markers)
                    │
         ┌─────────┼─────────┐
         │         │         │
      Agent 1   Agent 2   Agent 3
     (Claude)  (Claude)  (Ollama)
    Surveillance Specialist Advisory
```

## Manual Start (without scripts)

```bash
# Terminal 1: Backend
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python main.py

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
```

## Project Structure

```
├── sim/                    # Simulation engine
│   ├── drone_model.py      # Kinematic drone (haversine movement)
│   ├── world_state.py      # Markers, drones, tick loop
│   └── sensor_overlay.py   # Point-in-polygon sensor triggers
├── agents/                 # AI agent system
│   ├── agent1_surveillance.py  # Expanding circle survey
│   ├── agent2_specialist.py    # Swarm deployment
│   └── agent3_advisory.py      # Response plans (Ollama)
├── orchestrator/           # Deterministic state machine
├── frontend/src/           # React + Mapbox operator UI
├── main.py                 # FastAPI entry point
├── config.yaml             # Ports, models, scenario
├── setup.bat / setup.sh    # One-time setup
└── run.bat / run.sh        # Start everything
```

## Requirements

- Python 3.11+
- Node.js 22 LTS
- Anthropic API key (for agents)
- Mapbox token (for map display)
- Ollama (optional, for Agent 3 — falls back to deterministic mode)
