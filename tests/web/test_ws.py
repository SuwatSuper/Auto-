# Layer 3 — Infrastructure (tests/web/test_ws)
"""B3 regression: WebSocket status ticker must fire even under price flood."""
from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest
import structlog
from pydantic import SecretStr
from starlette.testclient import TestClient

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed
from infrastructure.web.api import create_app


def _make_runtime() -> PipelineRuntime:
    settings = Settings(persist_state=False, initial_capital="1000", dashboard_api_key=SecretStr(""), prices_topic="prices.thb_btc.v1")
    logger = structlog.get_logger("test")
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, logger, deps=deps)


@pytest.mark.asyncio
async def test_status_sent_even_under_price_flood() -> None:
    """B3: status messages must arrive within ~1.5s even when prices flood the bus."""
    runtime = _make_runtime()

    # Start the runtime so the bus is created
    await runtime.start("live")
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
