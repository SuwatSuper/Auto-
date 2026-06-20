# ============================================================
#  KINGDOM PRIME — รันตัวเดียวจบ (PowerShell)
# ============================================================
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "[1/3] Setting up environment (first time only)..." -ForegroundColor Cyan
    $created = $false
    foreach ($cmd in @("py -3.12", "py -3", "python")) {
        & cmd /c "$cmd -m venv venv" 2>$null
        if (Test-Path $Python) { $created = $true; break }
    }
    if (-not $created) { Write-Host "ERROR: Python 3.12 not found" -ForegroundColor Red; exit 1 }
    & $Python -m pip install --quiet --no-index --find-links=wheels -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      Offline wheels mismatch — installing online..." -ForegroundColor Yellow
        & $Python -m pip install --quiet -r requirements.txt
    }
    Write-Host "      Done." -ForegroundColor Green
}

Write-Host "[setup] Preparing config (.env)..." -ForegroundColor Cyan
& $Python (Join-Path $Root "scripts\setup_env.py")

Write-Host "[2/3] Starting Kingdom Prime server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$Root'; `$env:PYTHONPATH=Join-Path '$Root' 'src'; & '$Python' -m uvicorn main:app --host 127.0.0.1 --port 8000"

Write-Host "[3/3] Opening dashboard..." -ForegroundColor Cyan
Start-Sleep -Seconds 3
Start-Process "http://localhost:8000/"
Write-Host "Ready!  http://localhost:8000/" -ForegroundColor Green
