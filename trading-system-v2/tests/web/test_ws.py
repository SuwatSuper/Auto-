# Layer 3 — Infrastructure (tests/web/test_ws)
"""B3 regression: WebSocket status ticker must fire even under price flood."""
from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest
import structlog
from starlette.testclient import TestClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def _make_runtime() -> PipelineRuntime:
    settings = Settings(prices_topic="prices.thb_btc.v1")
    logger = structlog.get_logger("test")
    return PipelineRuntime(settings, logger)


@pytest.mark.asyncio
async def test_status_sent_even_under_price_flood() -> None:
    """B3: status messages must arrive within ~1.5s even when prices flood the bus."""
    runtime = _make_runtime()

    # Start the runtime so the bus is created
    await runtime.start("simulator")
    app = create_app(runtime)

    msgs: list[dict[str, object]] = []
    received_event = threading.Event()

    def _run_sync_client() -> None:
        try:
            with TestClient(app) as client, client.websocket_connect("/ws") as ws:
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    try:
                        ws.send_text(json.dumps({"type": "ping"}))
                        data = ws.receive_json()
                        msgs.append(data)  # type: ignore[arg-type]
                        if data.get("type") == "status":
                            received_event.set()
                            break
                    except Exception:
                        break
        except Exception:
            pass
        finally:
            received_event.set()

    t = threading.Thread(target=_run_sync_client, daemon=True)
    t.start()

    # Wait for the status message (up to 2.5s)
    deadline = asyncio.get_event_loop().time() + 2.5
    while asyncio.get_event_loop().time() < deadline:
        if received_event.is_set():
            break
        await asyncio.sleep(0.1)

    t.join(timeout=1.0)
    await runtime.stop()

    types = {m.get("type") for m in msgs}
    assert "status" in types, f"Expected 'status' message in WS stream but got types: {types}"
