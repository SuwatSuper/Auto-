# Tests — bug-audit fixes: circuit-breaker persistence (C1/L7) + risk-rule
# 0-semantics / off-by-one (M2/L1).
from __future__ import annotations

from decimal import Decimal

from domain.portfolio.models import Account
from domain.risk.circuit_breaker import CircuitBreaker
from domain.risk.rules import RiskLimits, evaluate
from domain.shared.money import Money
from domain.trading.orders import Order, OrderStatus, Side


def _thb(x: str) -> Money:
    return Money(amount=Decimal(x), currency="THB")


# ── C1: breaker survives a "restart" via to_dict / load_dict ─────────────
def test_breaker_snapshot_round_trips_open_state() -> None:
    b = CircuitBreaker(max_consecutive_losses=3)
    fired: list[int] = []
    b.on_change = lambda: fired.append(1)
    b.record_trade(Decimal("-1"), now=1000)
    b.record_trade(Decimal("-1"), now=1001)
    b.record_trade(Decimal("-1"), now=1002)  # 3rd loss -> auto-trip
    assert b.is_open
    assert fired  # on_change fired on the state changes
    # L7: auto-trip stamps the real epoch-seconds, not 1970.
    assert b.trip_history == ((1002, "CONSECUTIVE_LOSSES"),)

    snap = b.to_dict()
    # Fresh breaker after a restart (config default 0 = unlimited) stays closed…
    restored = CircuitBreaker(max_consecutive_losses=0)
    assert restored.is_open is False
    restored.load_dict(snap)
    # …until the persisted tripped state is restored.
    assert restored.is_open is True
    assert restored.consecutive_losses == 3
    # load_dict must NOT overwrite the live operator/config threshold…
    assert restored.max_consecutive_losses == 0
    # …and must NOT fire on_change (restoring is not a new event).
    fired2: list[int] = []
    b3 = CircuitBreaker()
    b3.on_change = lambda: fired2.append(1)
    b3.load_dict(snap)
    assert not fired2


def test_breaker_zero_threshold_never_auto_trips() -> None:
    b = CircuitBreaker(max_consecutive_losses=0)  # 0 = unlimited
    for _ in range(20):
        b.record_trade(Decimal("-1"), now=1)
    assert b.is_open is False
    assert b.consecutive_losses == 20


# ── M2: evaluate() honors 0 = UNLIMITED (must not reject every order) ─────
def _order() -> Order:
    return Order(order_id="o1", symbol="BTC_THB", side=Side.BUY, qty=Decimal("0.001"),
                 limit_price=None, status=OrderStatus.NEW, created_ms=0)


def _limits(**kw: object) -> RiskLimits:
    base: dict[str, object] = dict(
        max_order_qty=Decimal("1"), max_position_qty=Decimal("1"),
        max_daily_loss=_thb("100000"), max_drawdown_pct=Decimal("50"),
    )
    base.update(kw)
    return RiskLimits(**base)  # type: ignore[arg-type]


def _evaluate(limits: RiskLimits, **kw: object) -> object:
    common = dict(
        order=_order(),
        account=Account(account_id="a", cash=_thb("100000"), realized_pnl=_thb("0")),
        positions={}, daily_pnl=_thb("0"),
        peak_equity=_thb("100000"), current_equity=_thb("100000"),
    )
    common.update(kw)
    return evaluate(limits=limits, **common)  # type: ignore[arg-type]


def test_evaluate_zero_consecutive_losses_is_unlimited() -> None:
    dec = _evaluate(_limits(max_consecutive_losses=0), consecutive_losses=0)
    assert dec.approved is True  # 0 = unlimited, not "reject everything"
    dec5 = _evaluate(_limits(max_consecutive_losses=5), consecutive_losses=5)
    assert dec5.approved is False  # a real finite limit still binds


# ── L1: open-position cap is binding (>=), consistent with the live rail ──
def test_evaluate_open_positions_cap_is_binding() -> None:
    dec = _evaluate(_limits(max_open_positions=3), open_positions_count=3)
    assert dec.approved is False  # at the cap rejects (was '>' = allowed cap+1)
    dec_ok = _evaluate(_limits(max_open_positions=3), open_positions_count=2)
    assert dec_ok.approved is True
