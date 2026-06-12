# ============================================================
#  Trading System v2 — รันตัวเดียวจบ ไม่ต้องโหลดอะไรเพิ่ม
# ============================================================
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPath  = Join-Path $Root "venv"
$Python    = Join-Path $VenvPath "Scripts\python.exe"
$Wheels    = Join-Path $Root "wheels"

# สร้าง venv ครั้งแรกครั้งเดียว
if (-not (Test-Path $Python)) {
    Write-Host "[1/3] Setting up environment (first time only)..." -ForegroundColor Cyan
    python -m venv venv | Out-Null
    & $Python -m pip install --quiet --no-index --find-links=$Wheels `
        fastapi uvicorn websockets orjson structlog pydantic pydantic-settings httpx anyio h11 click
    Write-Host "      Done." -ForegroundColor Green
}

Write-Host "[2/3] Starting server..." -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $Root "src"
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$Root'; `$env:PYTHONPATH='src'; & '$Python' -m uvicorn main:app --host 0.0.0.0 --port 8000"

Write-Host "[3/3] Opening browser..." -ForegroundColor Cyan
Start-Sleep -Seconds 3
Start-Process "http://localhost:8000/"
Write-Host "Ready!  http://localhost:8000/" -ForegroundColor Green
