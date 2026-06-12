# Layer 1 — Domain (tests/domain/test_treasury)
"""Boundary tests for the pure treasury (account-guardian) rules."""
from __future__ import annotations

from decimal import Decimal

from domain.portfolio.treasury import (
    TreasuryLimits,
    VetoReason,
    review_open,
    should_halt,
    worst_case_loss,
)

D = Decimal
LIM = TreasuryLimits(initial_capital=D("1000"))  # floor 700, daily cap 50


def test_limits_hand_math() -> None:
    assert LIM.floor_equity() == D("700.00")
    assert LIM.daily_loss_cap() == D("50.00")


def test_approves_when_all_clear() -> None:
    d = review_open(D("1000"), D("1000"), D("0"), D("500"), D("20"), LIM, halted=False)
    assert d.approved is True and d.reasons == ()


def test_survival_floor_boundary() -> None:
    # equity 1000, worst case 300 → 700 == floor → still OK (not below)
    ok = review_open(D("1000"), D("1000"), D("0"), D("500"), D("300"), LIM, halted=False)
    assert ok.approved is True
    # worst case 300.01 → 699.99 < 700 → veto
    bad = review_open(D("1000"), D("1000"), D("0"), D("500"), D("300.01"), LIM, halted=False)
    assert bad.approved is False and VetoReason.SURVIVAL_FLOOR in bad.reasons


def test_daily_loss_boundary() -> None:
    ok = review_open(D("950.01"), D("950.01"), D("-49.99"), D("100"), D("10"), LIM, halted=False)
    assert VetoReason.DAILY_LOSS_LIMIT not in ok.reasons
    bad = review_open(D("950"), D("950"), D("-50"), D("100"), D("10"), LIM, halted=False)
    assert VetoReason.DAILY_LOSS_LIMIT in bad.reasons


def test_insufficient_cash_and_halted() -> None:
    d = review_open(D("100"), D("1000"), D("0"), D("100.01"), D("1"), LIM, halted=True)
    assert d.approved is False
    assert VetoReason.INSUFFICIENT_CASH in d.reasons
    assert VetoReason.HALTED in d.reasons


def test_should_halt_paths() -> None:
    assert should_halt(D("-50"), D("950"), LIM) is True      # daily cap hit
    assert should_halt(D("-49.99"), D("950.01"), LIM) is False
    assert should_halt(D("0"), D("699.99"), LIM) is True     # below floor
    assert should_halt(D("0"), D("700"), LIM) is False


def test_worst_case_loss_hand_math() -> None:
    # qty 0.001, entry 1.5M, stop 1.485M → 15 ; fees 3.75 + 3.72 → 22.47
    assert worst_case_loss(D("0.001"), D("1500000"), D("1485000"), D("3.75"), D("3.72")) == D("22.470")
