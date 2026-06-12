# ============================================================
#  Trading System v2 — One-click launcher (Windows PowerShell)
# ============================================================
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "=== Installing dependencies ===" -ForegroundColor Cyan
pip install fastapi "uvicorn[standard]" websockets orjson structlog pydantic "pydantic-settings" httpx --quiet

Write-Host "=== Creating entry point ===" -ForegroundColor Cyan
$mainPy = Join-Path $Root "src\main.py"
if (-not (Test-Path $mainPy)) {
    @"
from bootstrap import build_runtime
from infrastructure.web.api import create_app

app = create_app(build_runtime())
"@ | Set-Content -Path $mainPy -Encoding UTF8
    Write-Host "  Created src/main.py" -ForegroundColor Green
} else {
    Write-Host "  src/main.py already exists" -ForegroundColor Gray
}

Write-Host "=== Starting server ===" -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $Root "src"

Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$Root'; `$env:PYTHONPATH='src'; python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

Write-Host "  Waiting for server to start..." -ForegroundColor Gray
Start-Sleep -Seconds 3

Write-Host "=== Opening browser ===" -ForegroundColor Cyan
Start-Process "http://localhost:8000/"

Write-Host "Done! Dashboard: http://localhost:8000/" -ForegroundColor Green
