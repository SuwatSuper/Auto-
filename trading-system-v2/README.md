# AI Trading Platform — Phase 1

Real-time price pipeline (Bitkub WebSocket) + browser dashboard with agent controls.

## Quick Start (Windows + VS Code)

1. Extract this folder somewhere, e.g. `C:\trading-system`
2. Open the folder in VS Code → open Terminal (Ctrl + `)
3. Setup once:
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```
4. Run with simulator (no internet needed):
   ```powershell
   python scripts\run.py --simulator
   ```
5. Open browser: **http://localhost:8000**

For live Bitkub: `python scripts\run.py` (no flag).

Ctrl + C in terminal to stop everything.

## Dashboard Features

- Live THB_BTC price ticker
- 5-minute price chart (auto-updates)
- System health: mode, uptime, msg/sec, latency
- Agent controls: start / stop individual or all
- **EMERGENCY STOP** button — kills all agents instantly
- Mode switch: Live ↔ Simulator
- Recent events log (last 200)

## Run Tests

```powershell
pytest
```
