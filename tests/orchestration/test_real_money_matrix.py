# Layer 2 — Orchestration (tests/orchestration/test_real_money_matrix)
"""B1 real-money safety matrix.

A scenario matrix over the live-trading guard rails: the hard-coded order
ceiling (defense-in-depth), the operator per-order cap, the live-arming gates,
and the order-construction vetoes. Every row asserts that real money is only
ever spent inside the bounds the system promises.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog

from infrastructure.config import Settings
from orchestration.control import (
    HARD_CAP_DEPLOYABLE_THB,
    HARD_CAP_SINGLE_ORDER_THB,
    RiskSettings,
    validate_risk_settings,
)
from orchestration.runtime import PipelineRuntime

_LIVE = "I_ACCEPT_REAL_MONEY_RISK"
_MARK = Decimal("1500000")  # THB / BTC


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


def _armed_runtime(
    *, cap: str = "5000", reconciled: bool = True, balances: dict[str, str] | None = None
) -> tuple[PipelineRuntime, _MockGateway]:
    gw = _MockGateway()
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    assert rt._trader is not None
    rt._trader.mark_price = _MARK
    rt.settings.execution_engine = "live"  # type: ignore[attr-defined]
    rt.settings.live_trading_confirm = _LIVE  # type: ignore[attr-defined]
    rt._max_single_order_thb = Decimal(cap)
    rt._rest_gateway = gw
    rt.agents["risk_gate"].set_rest_gateway(gw)  # type: ignore[attr-defined]
    rt._reconciliation = _Recon(reconciled, balances or {"BTC": "10"})
    return rt, gw


def _baseline_settings() -> RiskSettings:
    return RiskSettings(
        risk_per_trade_pct=Decimal("1"),
        stop_pct=Decimal("0.5"),
        take_profit_pct=Decimal("1.5"),
        max_daily_loss_pct=Decimal("100"),
        max_consecutive_losses=0,
        max_open_positions=1,
        max_deployable_thb=Decimal("0"),
        max_single_order_thb=Decimal("0"),
    )


# ── 1. Hard cap enforced at the config validation layer ──────────────
@pytest.mark.parametrize(
    "field,value,ok",
    [
        ("max_single_order_thb", "5000", True),
        ("max_single_order_thb", str(HARD_CAP_SINGLE_ORDER_THB), True),          # == ceiling allowed
        ("max_single_order_thb", str(HARD_CAP_SINGLE_ORDER_THB + 1), False),     # over ceiling rejected
        ("max_single_order_thb", "999999999", False),
        ("max_deployable_thb", str(HARD_CAP_DEPLOYABLE_THB), True),
        ("max_deployable_thb", str(HARD_CAP_DEPLOYABLE_THB + 1), False),
    ],
)
def test_hard_cap_validation_matrix(field: str, value: str, ok: bool) -> None:
    settings, errors = validate_risk_settings(_baseline_settings(), {field: value})
    if ok:
        assert settings is not None and not errors
    else:
        assert settings is None
        assert any("hard cap" in e for e in errors)


# ── 2. Hard cap clamps the REAL order even if the field is set too high ──
def test_hard_cap_clamps_live_order_notional() -> None:
    rt, _ = _armed_runtime(cap="5000")
    # Bypass validation: directly set the field above the hard ceiling.
    rt._max_single_order_thb = HARD_CAP_SINGLE_ORDER_THB * 3
    spec = rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"})
    assert spec is not None
    notional = Decimal(spec["amount"])
    assert notional <= HARD_CAP_SINGLE_ORDER_THB           # never above the ceiling
    assert notional > HARD_CAP_SINGLE_ORDER_THB * Decimal("0.9")  # clamped to ~ceiling, not the 3x field


# ── 3. Operator per-order cap clamps the notional ────────────────────
@pytest.mark.parametrize("cap", ["5000", "10000", "250000"])
def test_per_order_cap_clamps_notional(cap: str) -> None:
    rt, _ = _armed_runtime(cap=cap)
    spec = rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"})
    assert spec is not None
    assert Decimal(spec["amount"]) <= Decimal(cap)


# ── 4. Live-arming gate matrix (set_execution_mode) ──────────────────
def _fresh_runtime() -> PipelineRuntime:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    return rt


def test_arm_requires_confirm_token() -> None:
    rt = _fresh_runtime()
    rt._max_single_order_thb = Decimal("5000")
    ok, payload = rt.set_execution_mode("live", confirm="nope")
    assert ok is False and "token" in str(payload)


def test_arm_requires_positive_cap() -> None:
    rt = _fresh_runtime()
    rt._max_single_order_thb = Decimal("0")
    ok, payload = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok is False and payload.get("field") == "max_single_order_thb"


def test_arm_rejects_cap_above_hard_ceiling() -> None:
    rt = _fresh_runtime()
    rt._max_single_order_thb = HARD_CAP_SINGLE_ORDER_THB + 1
    ok, payload = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok is False and "hard ceiling" in str(payload)


def test_arm_succeeds_with_valid_cap_and_token() -> None:
    rt = _fresh_runtime()
    rt._max_single_order_thb = Decimal("5000")
    ok, payload = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok is True
    assert payload["mode"] == "live"
    assert payload["all_gates_open"] is True


# ── 5. Order-construction veto matrix ────────────────────────────────
def test_treasury_halt_blocks_real_buy() -> None:
    rt, _ = _armed_runtime()
    assert rt._treasury is not None
    rt._treasury.halted = True
    assert rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"}) is None


def test_single_position_rule_blocks_second_buy() -> None:
    from domain.trading.paper import PaperPosition  # noqa: PLC0415

    rt, _ = _armed_runtime()
    spec1 = rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"})
    assert spec1 is not None
    # Simulate an open position; a second BUY must not build an order.
    assert rt._trader is not None
    rt._trader.position = PaperPosition(
        symbol="thb_btc",
        qty=Decimal("0.001"),
        entry_price=_MARK,
        stop_price=_MARK * Decimal("0.99"),
        take_profit_price=_MARK * Decimal("1.02"),
        entry_fee=Decimal("0"),
        opened_ms=0,
    )
    assert rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"}) is None


def test_sell_without_position_is_noop() -> None:
    rt, _ = _armed_runtime()
    assert rt._trader is not None and rt._trader.position is None
    assert rt._build_live_order({"signal": "SELL", "symbol": "thb_btc"}) is None


def test_below_exchange_minimum_is_rejected() -> None:
    # A cap so small the notional falls under Bitkub's minimum → no doomed order.
    rt, _ = _armed_runtime(cap="11")  # ~11 THB target, below min once sized
    rt.settings.bitkub_min_order_thb = "10000"  # type: ignore[attr-defined]
    assert rt._build_live_order({"signal": "BUY", "symbol": "thb_btc"}) is None


@pytest.mark.asyncio
async def test_manual_buy_blocked_when_unreconciled() -> None:
    rt, gw = _armed_runtime(reconciled=False)
    assert rt._live_orders_armed() is False
    await rt.manual_order("BUY")
    assert gw.bids == []  # no real money spent against an unverified account


# ── 6. Protective close never over-sells the real wallet (C2) ────────
@pytest.mark.asyncio
async def test_live_close_capped_to_real_balance() -> None:
    rt, gw = _armed_runtime(balances={"BTC": "0.3"})
    await rt._live_close(Decimal("1.0"), _MARK)  # paper thinks 1.0 BTC
    assert len(gw.asks) == 1
    assert Decimal(gw.asks[0][1]) == Decimal("0.3")
