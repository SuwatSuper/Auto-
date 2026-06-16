@echo off
REM ============================================================
REM  KINGDOM PRIME — one-click start (Windows)
REM  ดับเบิลคลิกไฟล์นี้: สร้าง venv -> ติดตั้ง -> ใส่คีย์ -> รัน -> เปิดเบราว์เซอร์
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [1/4] Setting up environment - first time only...
    py -3.12 -m venv venv 2>nul || py -3 -m venv venv 2>nul || python -m venv venv
    if not exist "%PY%" (
        echo ERROR: Python 3.11+ not found. Install Python 3.12 from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    REM Bundled offline wheels target Python 3.12 x64 (your machine)
    "%PY%" -m pip install --quiet --no-index --find-links=wheels -r requirements.txt
    if errorlevel 1 (
        echo       Offline wheels did not match this Python - installing online...
        "%PY%" -m pip install --quiet -r requirements.txt
        if errorlevel 1 (
            echo ERROR: dependency install failed. Check your internet connection.
            pause
            exit /b 1
        )
    )
    echo       Done.
)

echo [2/4] Preparing config (.env)...
REM Non-interactive: creates .env + a private control key. Connect your Bitkub
REM account in ONE place — the dashboard "Connect" form. No prompt here.
"%PY%" scripts\setup_env.py

echo [3/4] Starting Kingdom Prime server on http://localhost:8000 ...
set "PYTHONPATH=%~dp0src"
start "KINGDOM PRIME SERVER" cmd /k ""%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo [4/4] Opening dashboard...
timeout /t 3 /nobreak >nul
start "" "http://localhost:8000/"
echo.
echo  Ready!  Dashboard: http://localhost:8000/
echo  To change your API key later: delete .env and run start.bat again.
echo  Close the server window to stop.
endlocal
