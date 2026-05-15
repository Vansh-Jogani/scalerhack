#!/bin/bash
set -e

echo "============================================"
echo " ARIA v1 - Setup"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Install Python 3.11+"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Install Node 22 LTS"
    exit 1
fi

echo "[1/4] Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "[2/4] Installing Python dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "[3/4] Installing frontend dependencies..."
cd frontend
npm install --silent
cd ..

echo "[4/4] Setting up environment file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "!! IMPORTANT: Edit .env and add your API keys !!"
    echo "   - ANTHROPIC_API_KEY from https://console.anthropic.com/"
    echo "   - MAPBOX_TOKEN from https://account.mapbox.com/access-tokens/"
    echo ""
fi
if [ ! -f "frontend/.env" ]; then
    cp frontend/.env.example frontend/.env
    echo "!! IMPORTANT: Edit frontend/.env and add your Mapbox token !!"
    echo ""
fi

echo "============================================"
echo " Setup complete!"
echo " Next: Edit .env and frontend/.env with your API keys"
echo " Then: ./run.sh to start the system"
echo "============================================"
