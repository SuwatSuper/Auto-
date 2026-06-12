# Runbook

## Starting the system

```bash
cd trading-system-v2
pip install -e ".[dev]"
python scripts/run.py
```

## Emergency stop

POST /api/emergency_stop — stops all agents and supervisor immediately.

## Emergency reset

POST /api/emergency_reset — clears the emergency_stopped flag without auto-starting.

## Switching modes

POST /api/mode/simulator — switch to simulated price feed.
POST /api/mode/live — switch to live Bitkub WebSocket feed.

## Checking status

GET /api/status — returns current mode, uptime, latency, agents.

## Kingdom Prime ops
- Start: start.bat (Windows) / start.sh (mac+Linux) / start.ps1 → http://localhost:8000/
- Control plane: every POST /api/* needs header X-API-Key == DASHBOARD_API_KEY (.env).
  Rotate by editing .env and restarting. Empty key = guard off (dev only).
- EMERGENCY STOP halts feed+agents; RESET clears the flag only — press Start All
  or switch mode to resume (by design, B2).
