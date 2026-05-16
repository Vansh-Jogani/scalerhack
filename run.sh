#!/bin/bash
set -e

echo "============================================"
echo " ARIA v1 - Starting..."
echo "============================================"
echo ""

# Check .env exists
if [ ! -f ".env" ]; then
    echo "[ERROR] .env not found. Run ./setup.sh first."
    exit 1
fi

# Activate venv
if [ ! -d "venv" ]; then
    echo "[ERROR] Virtual environment not found. Run ./setup.sh first."
    exit 1
fi
source venv/bin/activate

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "[1/2] Starting backend (FastAPI on port 8000)..."
source venv/bin/activate
python3 main.py &
BACKEND_PID=$!

echo "[2/2] Starting frontend (Vite)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "=================================================="
echo " ARIA V1 SIMULATION RUNNING"
echo " Backend:  http://localhost:8000/health"
echo " Frontend: http://localhost:5173"
echo ""
echo " Press Ctrl+C to stop"
echo "============================================"
echo ""

# Wait for either process to exit
wait
