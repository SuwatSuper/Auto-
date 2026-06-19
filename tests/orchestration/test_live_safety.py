# Layer 2 — Orchestration (tests/orchestration/test_live_safety)
"""Real-money safety regressions from the deep latent-bug audit:
- C1: a real BUY must NOT fire when the treasury would veto (halted/underfunded).
- C2: a protective close must not ask for more coin than is really held.
- M2: live orders don't arm against an unverified (unreconciled) account.
- M6: non-finite (NaN/Infinity) prices are rejected, not crashed on."""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime

_LIVE = "I_ACCEPT_REAL_MONEY_RISK"


class _MockGateway:
    def __init__(self) -> None:
        self.bids: list[tuple[str, str, str, str]] = []
        self.asks: list[tuple[str, str, str, str]] = []

    async def place_bid(self, sym: str, amount: str, rate: str, typ: str = "market") -> dict[str, object]:
        self.bids.append((sym, amount, rate, typ))
        return {"error": 0, "result": {"id": 1}}

    async def place_ask(self, sym: str, amount: str, rate: str, typ: str = "market") -> dict[str, object]:
        self.asks.append((sym, amount, rate, typ))
        return {"error": 0, "result": {"id": 2}}


class _Recon:
    def __init__(self, reconciled: bool, balances: dict[str, str]) -> None:
        self.is_reconciled = reconciled
        self.last_balances = balances


def _armed_runtime(gw: _MockGateway, *, reconciled: bool = True, balances: dict[str, str] | None = None) -> PipelineRuntime:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    assert rt._trader is not None
    rt._trader.mark_price = Decimal("1500000")
    rt.settings.execution_engine = "live"           # type: ignore[attr-defined]
    rt.settings.live_trading_confirm = _LIVE          # type: ignore[attr-defined]
    rt._max_single_order_thb = Decimal("5000")
    rt._rest_gateway = gw
    rt.agents["risk_gate"].set_rest_gateway(gw)        # type: ignore[attr-defined]
    rt._reconciliation = _Recon(reconciled, balances or {"BTC": "10"})
    return rt


# ── C1: treasury veto blocks the REAL order ──────────────────────────
def test_no_live_bid_built_when_treasury_halted() -> None:
    gw = _MockGateway()
    rt = _armed_runtime(gw)
    assert rt._live_orders_armed() is True
    assert rt._treasury is not None
    rt._treasury.halted = True  # daily-loss / survival-floor halt
    spec = rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"})
    assert spec is None  # would have fired a real bid against a halted account


@pytest.mark.asyncio
async def test_manual_live_buy_does_not_fire_when_halted() -> None:
    gw = _MockGateway()
    rt = _armed_runtime(gw)
    assert rt._treasury is not None
    rt._treasury.halted = True
    ok, _ = await rt.manual_order("BUY")
    assert gw.bids == []          # NO real money spent
    assert rt._trader.position is None  # type: ignore[union-attr]


# ── C2: protective close capped to the real wallet balance ───────────
@pytest.mark.asyncio
async def test_live_close_caps_qty_to_real_balance() -> None:
    gw = _MockGateway()
    # paper thinks it holds 1.0 BTC; the real wallet only has 0.3 BTC
    rt = _armed_runtime(gw, balances={"BTC": "0.3"})
    await rt._live_close(Decimal("1.0"), Decimal("1500000"))
    assert len(gw.asks) == 1
    assert Decimal(gw.asks[0][1]) == Decimal("0.3")  # never over-sell


# ── M2: unverified account → not armed (degrade to paper) ────────────
def test_not_armed_when_account_unreconciled() -> None:
    gw = _MockGateway()
    rt = _armed_runtime(gw, reconciled=False)
    assert rt._live_orders_armed() is False


# ── M6: non-finite prices rejected, not crashed ──────────────────────
@pytest.mark.asyncio
async def test_manual_order_rejects_non_finite_price() -> None:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    rt._trader.mark_price = Decimal("1500000")  # type: ignore[union-attr]
    for bad in ("NaN", "Infinity", "-Infinity", "0"):
        ok, payload = await rt.manual_order("BUY", bad)
        assert ok is False
        assert "bad price" in str(payload)
