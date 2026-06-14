# Layer 3 — Infrastructure (tests/web/test_real_trader_journey)
"""End-to-end 'real trader' capability proof, exercised through the real API +
runtime: paper buy/sell, the paper⇄live toggle (token-gated), a LIVE order that
actually fires a Bitkub bid/ask through a mock signed gateway, and the honest
absence of any real-money withdrawal feature.

These use the ASGI app WITHOUT the lifespan (so the 181-agent pipeline is not
running) — agents are built and a mark price is set directly, which makes the
manual order path deterministic.
"""
from __future__ import annotations

from decimal import Decimal

import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed

_LIVE = "I_ACCEPT_REAL_MONEY_RISK"


class _MockGateway:
    """Stand-in for the signed Bitkub REST gateway (records real order calls)."""

    def __init__(self) -> None:
        self.bids: list[tuple[str, str, str, str]] = []
        self.asks: list[tuple[str, str, str, str]] = []

    async def place_bid(self, sym: str, amount: str, rate: str, typ: str = "market") -> dict[str, object]:
        self.bids.append((sym, amount, rate, typ))
        return {"error": 0, "result": {"id": len(self.bids)}}

    async def place_ask(self, sym: str, amount: str, rate: str, typ: str = "market") -> dict[str, object]:
        self.asks.append((sym, amount, rate, typ))
        return {"error": 0, "result": {"id": len(self.asks)}}


def _runtime() -> PipelineRuntime:
    settings = Settings(
        persist_state=False, news_enabled=False, initial_capital="1000000",
        prices_topic="prices.thb_btc.v1",
    )
    deps = RuntimeDeps(
        bus=InMemoryEventBus(), clock=SystemClock(), state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(), feed_factory=lambda _m: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    rt = PipelineRuntime(settings, structlog.get_logger("trader"), deps=deps)
    rt.agents = rt._make_agents()            # build agents, do NOT start the loops
    assert rt._trader is not None
    rt._trader.mark_price = Decimal("1500000")  # deterministic mark
    return rt


def _client(rt: PipelineRuntime) -> AsyncClient:
    transport = ASGITransport(app=create_app(rt))  # lifespan not run by ASGITransport
    return AsyncClient(transport=transport, base_url="http://test")


# ── 1. Buy & sell coins (paper) through the real API ─────────────────
async def test_real_trader_can_buy_and_sell_paper() -> None:
    rt = _runtime()
    async with _client(rt) as c:
        # BUY a coin
        r = await c.post("/api/order", json={"side": "BUY"})
        assert r.status_code == 200, r.text
        assert rt._trader.position is not None  # holding BTC now

        # SELL / close the position
        r2 = await c.post("/api/positions/close")
        assert r2.status_code == 200, r2.text
        assert rt._trader.position is None
        assert rt._trader.trades_closed >= 1


# ── 2. Paper⇄live toggle (the "trade air vs trade real" switch) ──────
async def test_paper_live_toggle_is_token_gated() -> None:
    rt = _runtime()
    async with _client(rt) as c:
        assert (await c.get("/api/execution/mode")).json()["mode"] == "paper"

        # live WITHOUT the confirm token → refused
        r = await c.post("/api/execution/mode", json={"mode": "live"})
        assert r.status_code == 400

        # live WITH token but no per-order cap → refused (real-money safety)
        r = await c.post("/api/execution/mode", json={"mode": "live", "confirm": _LIVE})
        assert r.status_code == 400
        assert "max_single_order_thb" in r.text

        # set a per-order cap, then arming live succeeds
        await c.post("/api/risk/settings", json={"max_single_order_thb": "5000"})
        r = await c.post("/api/execution/mode", json={"mode": "live", "confirm": _LIVE})
        assert r.status_code == 200 and r.json()["mode"] == "live"

        # toggle back to paper freely
        r = await c.post("/api/execution/mode", json={"mode": "paper"})
        assert r.status_code == 200 and r.json()["mode"] == "paper"


# ── 3. LIVE: a real Bitkub bid/ask actually fires when fully armed ───
async def test_live_order_fires_real_bid_and_ask_when_armed() -> None:
    rt = _runtime()
    gw = _MockGateway()
    # arm all four gates + wire the signed gateway
    rt.settings.execution_engine = "live"            # type: ignore[attr-defined]
    rt.settings.live_trading_confirm = _LIVE          # type: ignore[attr-defined]
    rt._max_single_order_thb = Decimal("5000")        # per-order cap set
    rt._rest_gateway = gw
    rt.agents["risk_gate"].set_rest_gateway(gw)        # type: ignore[attr-defined]
    assert rt._live_orders_armed() is True

    # a manual BUY now places a REAL bid on Bitkub
    ok, payload = await rt.manual_order("BUY")
    assert ok, payload
    assert len(gw.bids) == 1, "live BUY did not place a real bid"
    assert rt._trader.position is not None
    # notional respected the per-order cap
    assert Decimal(gw.bids[0][1]) <= Decimal("5000")

    # closing the live-backed position places a REAL ask
    ok2, _ = await rt.manual_order("CLOSE")
    assert ok2
    assert len(gw.asks) == 1, "closing a live position did not place a real ask"


def test_live_orders_not_armed_in_paper_mode() -> None:
    rt = _runtime()
    # default paper → never armed even if a gateway is attached
    rt._rest_gateway = _MockGateway()
    assert rt._live_orders_armed() is False


# ── 4. Honest: there is NO real-money withdrawal feature ─────────────
async def test_no_withdrawal_capability_exists() -> None:
    rt = _runtime()
    app = create_app(rt)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any("withdraw" in p.lower() for p in paths), "unexpected withdrawal route"
    assert not any("withdraw" in d.lower() for d in dir(rt)), "unexpected withdrawal method"
