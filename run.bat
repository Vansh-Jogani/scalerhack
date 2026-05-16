@echo off
echo ============================================
echo  ARIA v1 - Starting...
echo ============================================
echo.

:: Check .env exists
if not exist ".env" (
    echo [ERROR] .env not found. Run setup.bat first.
    pause
    exit /b 1
)

:: Activate venv
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

echo [1/2] Starting backend (FastAPI on port 8000)...
start "ARIA Backend" cmd /k "venv\Scripts\activate && python main.py"

echo [2/2] Starting frontend (Vite on port 5173)...
cd frontend
start "ARIA Frontend" cmd /k "npm run dev"
cd ..

:: Wait for servers to start
timeout /t 3 /nobreak > nul

echo.
echo ============================================
echo  ARIA v1 is running!
echo.
echo  Backend:  http://localhost:8000/health
echo  Frontend: http://localhost:5173
echo.
echo  Close this window to stop both servers.
echo ============================================
echo.

:: Open browser
start http://localhost:5173

:: Keep window open
pause
