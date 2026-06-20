# Layer 1 — Domain (backtest/statistics)
"""Pure statistics for judging whether a backtest edge is REAL, not luck.

No system can promise certain profit — markets are non-stationary and the future
is unknown. What we *can* do is quantify confidence honestly: is the mean trade
return distinguishable from zero (t-test), how risk-adjusted is it (Sharpe), and
what is a conservative lower bound on expectancy? A high t-statistic over many
out-of-sample trades is the strongest *honest* evidence of an edge — never a
guarantee.

Decimal-only, deterministic (no RNG — Monte Carlo resampling lives outside the
pure domain, in scripts/validate_profit.py).
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel

# Two-sided normal critical value for ~95% confidence (large-sample approximation
# to Student's t; honest for n ≳ 30, slightly optimistic for tiny samples).
_Z95 = Decimal("1.96")


class SignificanceReport(BaseModel, frozen=True):
    """How confident we can be that a set of trade returns has positive edge."""

    n: int
    mean: Decimal
    stddev: Decimal
    std_error: Decimal
    t_statistic: Decimal
    sharpe: Decimal
    ci95_low: Decimal
    ci95_high: Decimal
    significant_95: bool  # mean significantly > 0 at ~95% (t > 1.96 and n >= 2)


def mean(xs: Sequence[Decimal]) -> Decimal:
    """Arithmetic mean; 0 for an empty sequence."""
    if not xs:
        return Decimal(0)
    return sum(xs, Decimal(0)) / Decimal(len(xs))


def stddev(xs: Sequence[Decimal], *, sample: bool = True) -> Decimal:
    """Standard deviation. Sample (n-1) by default; 0 when undefined."""
    n = len(xs)
    if n < 2:
        return Decimal(0)
    mu = mean(xs)
    ss = sum(((x - mu) * (x - mu) for x in xs), Decimal(0))
    denom = Decimal(n - 1) if sample else Decimal(n)
    var = ss / denom
    if var <= 0:
        return Decimal(0)
    return var.sqrt()


def t_statistic(xs: Sequence[Decimal]) -> Decimal:
    """t = mean / standard_error. 0 when it cannot be computed (n<2 or std=0)."""
    n = len(xs)
    if n < 2:
        return Decimal(0)
    sd = stddev(xs)
    if sd <= 0:
        return Decimal(0)
    se = sd / Decimal(n).sqrt()
    if se <= 0:
        return Decimal(0)
    return mean(xs) / se


def sharpe(xs: Sequence[Decimal]) -> Decimal:
    """Per-trade Sharpe ratio (mean / stddev). 0 when std is 0 or n<2."""
    sd = stddev(xs)
    if sd <= 0:
        return Decimal(0)
    return mean(xs) / sd


def significance(xs: Sequence[Decimal]) -> SignificanceReport:
    """Full significance report for a sequence of per-trade returns."""
    n = len(xs)
    mu = mean(xs)
    sd = stddev(xs)
    se = sd / Decimal(n).sqrt() if n >= 2 and sd > 0 else Decimal(0)
    t = mu / se if se > 0 else Decimal(0)
    margin = _Z95 * se
    return SignificanceReport(
        n=n,
        mean=mu,
        stddev=sd,
        std_error=se,
        t_statistic=t,
        sharpe=sharpe(xs),
        ci95_low=mu - margin,
        ci95_high=mu + margin,
        significant_95=n >= 2 and se > 0 and t > _Z95,
    )
