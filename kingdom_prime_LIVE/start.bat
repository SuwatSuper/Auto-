@echo off
REM ============================================================
REM  KINGDOM PRIME — one-click start (Windows)
REM  ดับเบิลคลิกไฟล์นี้: สร้าง venv -> ติดตั้ง -> รัน -> เปิดเบราว์เซอร์
REM ============================================================
setlocal
cd /d "%~dp0"

REM First run: create .env from the template so the app has its config file.
REM ใส่ BITKUB_API_KEY / BITKUB_API_SECRET ในไฟล์ .env นี้ (เปิดด้วย Notepad)
if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [setup] Created .env  -- put your Bitkub API key/secret in this file.
    )
)

set "PY=venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [1/3] Setting up environment - first time only...
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

echo [2/3] Starting Kingdom Prime server on http://localhost:8000 ...
set "PYTHONPATH=%~dp0src"
start "KINGDOM PRIME SERVER" cmd /k ""%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo [3/3] Opening dashboard...
timeout /t 3 /nobreak >nul
start "" "http://localhost:8000/"
echo.
echo  Ready!  Dashboard: http://localhost:8000/   (classic UI: /classic)
echo  Close the server window to stop.
endlocal
