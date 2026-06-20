# Layer 1 — Domain (tests/domain/test_statistics)
"""Unit tests for the edge-significance statistics (Decimal-only)."""
from __future__ import annotations

from decimal import Decimal

from domain.backtest.statistics import (
    mean,
    sharpe,
    significance,
    stddev,
    t_statistic,
)


def _d(values: list[float | int | str]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


def test_mean_and_stddev_known_values() -> None:
    xs = _d([2, 4, 4, 4, 5, 5, 7, 9])  # textbook: mean 5, sample std ~2.138
    assert mean(xs) == Decimal(5)
    sd = stddev(xs)
    assert Decimal("2.13") < sd < Decimal("2.14")


def test_empty_and_degenerate_are_safe() -> None:
    assert mean([]) == Decimal(0)
    assert stddev([Decimal(3)]) == Decimal(0)  # n<2
    assert t_statistic([Decimal(3)]) == Decimal(0)
    assert sharpe(_d([5, 5, 5])) == Decimal(0)  # zero variance


def test_strong_consistent_edge_is_significant() -> None:
    # many small positive returns with low variance -> large t, significant
    xs = _d([12, 8, 10, 9, 11, 10, 13, 7, 9, 11, 10, 12, 8, 10, 9, 11])
    rep = significance(xs)
    assert rep.mean > 0
    assert rep.t_statistic > Decimal("1.96")
    assert rep.significant_95 is True
    assert rep.ci95_low > 0  # whole 95% interval above zero


def test_noisy_zero_mean_is_not_significant() -> None:
    xs = _d([100, -98, 95, -102, 99, -97, 101, -100, 96, -94])
    rep = significance(xs)
    assert rep.significant_95 is False
    assert rep.ci95_low < 0 < rep.ci95_high  # interval straddles zero


def test_sharpe_positive_for_positive_edge() -> None:
    assert sharpe(_d([1, 2, 1, 2, 1, 2])) > 0
