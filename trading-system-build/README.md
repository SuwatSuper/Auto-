# AI Trading Platform — Phase 1 (Price Pipeline)

## Quick Start (Windows + VS Code)

1. Extract this folder somewhere, e.g. `C:\trading-system`
2. Open the folder in VS Code
3. Open Terminal (Ctrl + `) and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

4. Run tests:

```powershell
pytest
```

5. Run pipeline (simulator — no network):

```powershell
python scripts\run_pipeline.py --simulator
```

6. Run pipeline (live Bitkub WebSocket):

```powershell
python scripts\run_pipeline.py
```

Press `Ctrl + C` to stop.

## Architecture

- Layer 1 (`src/domain/`) — pure business logic, fully tested
- Layer 2 (`src/orchestration/`) — asyncio coordination
- Layer 3 (`src/infrastructure/`) — WebSocket, in-memory event bus, config

In-memory event bus is a temporary Phase 1 implementation; the `EventPublisher` Protocol lets us swap to Redpanda/Kafka later without touching Layer 1 or 2.
