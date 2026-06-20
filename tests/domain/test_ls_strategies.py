# Layer 1 — Domain (tests/domain/test_ls_strategies)
"""Long/short strategies must emit BOTH BUY and SELL with correctly-sided brackets."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.strategy.base import SignalAction
from domain.strategy.breakout_ls import BreakoutLongShortStrategy
from domain.strategy.momentum_ls import MomentumLongShortStrategy
from domain.strategy.registry import get
from domain.strategy.reversion_ls import ReversionLongShortStrategy


def _df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.002 for c in closes],
            "low": [c * 0.998 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


def _scan(strat: object, df: pd.DataFrame, start: int):
    """Collect signals across growing windows; return list of OhlcvSignal."""
    sigs = []
    for i in range(start, len(df) + 1):
        sigs.append(strat.decide_df(df.iloc[:i]))  # type: ignore[attr-defined]
    return sigs


def test_registered() -> None:
    assert get("momentum_ls") is MomentumLongShortStrategy
    assert get("reversion_ls") is ReversionLongShortStrategy
    assert get("breakout_ls") is BreakoutLongShortStrategy


def test_breakout_emits_buy_on_new_high_and_sell_on_new_low() -> None:
    up = _df([100.0 + i for i in range(60)])  # monotonic up → new highs → BUY
    down = _df([100.0 - i * 0.5 for i in range(60)])  # monotonic down → new lows → SELL
    strat = BreakoutLongShortStrategy()
    up_actions = {strat.decide_df(up.iloc[:i]).action for i in range(36, len(up) + 1)}
    down_actions = {strat.decide_df(down.iloc[:i]).action for i in range(36, len(down) + 1)}
    assert SignalAction.BUY in up_actions
    assert SignalAction.SELL in down_actions


def test_breakout_short_bracket_is_correctly_sided() -> None:
    down = _df([100.0 - i * 0.5 for i in range(60)])
    strat = BreakoutLongShortStrategy()
    for i in range(36, len(down) + 1):
        sig = strat.decide_df(down.iloc[:i])
        if sig.action == SignalAction.SELL:
            entry = down["close"].iloc[i - 1]
            assert sig.stop_price is not None and sig.take_profit_price is not None
            assert float(sig.stop_price) > entry > float(sig.take_profit_price)
            return
    raise AssertionError("no SELL signal produced")


# down → up → down, so EMA fast crosses ABOVE (BUY) then BELOW (SELL) mid-series.
_MOM = (
    [100.0 - i * 0.5 for i in range(20)]
    + [90.0 + i * 1.0 for i in range(35)]
    + [124.0 - i * 1.0 for i in range(30)]
)


def test_momentum_emits_buy_and_sell() -> None:
    sigs = _scan(MomentumLongShortStrategy(), _df(_MOM), 23)
    actions = {s.action for s in sigs}
    assert SignalAction.BUY in actions
    assert SignalAction.SELL in actions


def test_momentum_short_bracket_is_correctly_sided() -> None:
    strat = MomentumLongShortStrategy()
    df = _df(_MOM)
    for i in range(23, len(_MOM) + 1):
        sig = strat.decide_df(df.iloc[:i])
        if sig.action == SignalAction.SELL:
            entry = df["close"].iloc[i - 1]
            assert sig.stop_price is not None and sig.take_profit_price is not None
            assert float(sig.stop_price) > entry > float(sig.take_profit_price)
            return
    raise AssertionError("no SELL signal produced")


def test_reversion_emits_buy_on_drop_and_sell_on_rise() -> None:
    closes = [100.0 - i * 0.6 for i in range(30)] + [82.0 + i * 0.8 for i in range(30)]
    sigs = _scan(ReversionLongShortStrategy(), _df(closes), 16)
    actions = {s.action for s in sigs}
    assert SignalAction.BUY in actions
    assert SignalAction.SELL in actions


def test_reversion_deterministic_and_insufficient_data() -> None:
    strat = ReversionLongShortStrategy()
    df = _df([100.0 - i * 0.6 for i in range(30)])
    assert strat.decide_df(df) == strat.decide_df(df)  # deterministic
    assert strat.decide_df(df.iloc[:5]).reason == "insufficient_data"
    # tunable thresholds are honoured
    tight = ReversionLongShortStrategy(oversold=Decimal("45"))
    assert tight.oversold == Decimal("45")
