# Tests — manual trade command + alerts
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import structlog

from infrastructure.alerts.notifier import AlertNotifier
from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


def _rt(**kw: object) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, **kw), logger=structlog.get_logger("t")
    )
    rt.agents = rt._make_agents()
    return rt


# ── manual order / close (paper) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_buy_then_close_changes_real_paper_portfolio() -> None:
    rt = _rt()
    assert rt._trader is not None
    ok, payload = await rt.manual_order("BUY", price="1500000")
    assert ok, payload
    assert rt._trader.open_positions() == 1
    # portfolio surfaced with real mark
    port = rt._trader.get_portfolio()
    assert port and port[0]["symbol"]
    # close it
    ok2, payload2 = await rt.manual_order("CLOSE", price="1510000")
    assert ok2, payload2
    assert rt._trader.open_positions() == 0


@pytest.mark.asyncio
async def test_manual_buy_blocked_when_breaker_open() -> None:
    rt = _rt()
    rt.trip_breaker("test")
    ok, payload = await rt.manual_order("BUY", price="1500000")
    assert not ok
    assert "breaker" in str(payload).lower()


@pytest.mark.asyncio
async def test_manual_buy_rejects_second_position() -> None:
    rt = _rt()
    assert (await rt.manual_order("BUY", price="1500000"))[0] is True
    ok, payload = await rt.manual_order("BUY", price="1500000")
    assert not ok
    assert "already open" in str(payload).lower()


@pytest.mark.asyncio
async def test_close_all_flattens() -> None:
    rt = _rt()
    await rt.manual_order("BUY", price="1500000")
    assert rt._trader.open_positions() == 1  # type: ignore[union-attr]
    res = await rt.close_all()
    assert res["ok"] is True
    assert rt._trader.open_positions() == 0  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_manual_order_bad_side() -> None:
    rt = _rt()
    ok, payload = await rt.manual_order("HODL", price="1500000")
    assert not ok
    assert "unknown side" in str(payload).lower()


# ── alert notifier (network-free via injected client) ────────────────

class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})


@pytest.mark.asyncio
async def test_notifier_noop_when_unconfigured() -> None:
    n = AlertNotifier()
    assert n.configured is False
    assert await n.send("hello") is False
    assert n.last_message == "hello"  # still recorded


@pytest.mark.asyncio
async def test_notifier_webhook_delivers() -> None:
    transport = _MockTransport()
    client = httpx.AsyncClient(transport=transport)
    n = AlertNotifier(webhook_url="https://example.com/hook", client=client)
    assert n.configured is True
    assert await n.send("alarm", "critical") is True
    assert n.sent_count == 1
    assert any("example.com" in c for c in transport.calls)
    await client.aclose()


@pytest.mark.asyncio
async def test_notifier_telegram_delivers() -> None:
    transport = _MockTransport()
    client = httpx.AsyncClient(transport=transport)
    n = AlertNotifier(telegram_bot_token="tok", telegram_chat_id="123", client=client)
    assert await n.send("ping") is True
    assert any("telegram.org" in c for c in transport.calls)
    await client.aclose()


@pytest.mark.asyncio
async def test_runtime_send_alert_uses_injected_notifier() -> None:
    rt = _rt()
    transport = _MockTransport()
    client = httpx.AsyncClient(transport=transport)
    rt._notifier = AlertNotifier(webhook_url="https://example.com/h", client=client)
    assert await rt.send_alert("test") is True
    await client.aclose()
