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
