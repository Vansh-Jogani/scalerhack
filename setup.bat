@echo off
echo ============================================
echo  ARIA v1 - Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node 22 LTS from nodejs.org
    pause
    exit /b 1
)

echo [1/4] Creating Python virtual environment...
if not exist "venv" (
    python -m venv venv
)

echo [2/4] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet

echo [3/4] Installing frontend dependencies...
cd frontend
call npm install --silent
cd ..

echo [4/4] Setting up environment file...
if not exist ".env" (
    copy .env.example .env
    echo.
    echo !! IMPORTANT: Edit .env and add your API keys !!
    echo    - ANTHROPIC_API_KEY from https://console.anthropic.com/
    echo    - MAPBOX_TOKEN from https://account.mapbox.com/access-tokens/
    echo.
)
if not exist "frontend\.env" (
    copy frontend\.env.example frontend\.env
    echo !! IMPORTANT: Edit frontend\.env and add your Mapbox token !!
    echo.
)

echo ============================================
echo  Setup complete!
echo  Next: Edit .env and frontend\.env with your API keys
echo  Then: run.bat to start the system
echo ============================================
pause
