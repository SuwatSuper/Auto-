# Layer 1 — Domain (tests/domain/test_circuit_breaker)
"""Tests for the CircuitBreaker pure state machine."""
from __future__ import annotations

from decimal import Decimal

from domain.risk.circuit_breaker import CircuitBreaker


def test_initially_closed() -> None:
    cb = CircuitBreaker(max_consecutive_losses=3)
    assert cb.is_open is False
    assert cb.trip_history == ()


def test_trip_opens_breaker_and_records_history() -> None:
    cb = CircuitBreaker()
    cb.trip("TEST_REASON", 1700000000)
    assert cb.is_open is True
    assert cb.trip_history == ((1700000000, "TEST_REASON"),)


def test_stays_open_after_multiple_trips() -> None:
    cb = CircuitBreaker()
    cb.trip("REASON_A", 100)
    cb.trip("REASON_B", 200)
    assert cb.is_open is True
    assert len(cb.trip_history) == 2


def test_reset_wrong_token_returns_false_stays_open() -> None:
    cb = CircuitBreaker()
    cb.trip("REASON", 100)
    result = cb.reset("wrong-token", 200)
    assert result is False
    assert cb.is_open is True


def test_reset_correct_token_closes_breaker() -> None:
    cb = CircuitBreaker()
    cb.trip("REASON", 100)
    result = cb.reset("MANUAL_RESET_CONFIRMED", 200)
    assert result is True
    assert cb.is_open is False


def test_record_trade_consecutive_losses_auto_trip() -> None:
    cb = CircuitBreaker(max_consecutive_losses=3)
    cb.record_trade(Decimal("-500"))
    assert cb.is_open is False
    cb.record_trade(Decimal("-500"))
    assert cb.is_open is False
    cb.record_trade(Decimal("-500"))
    assert cb.is_open is True


def test_record_trade_win_resets_counter() -> None:
    cb = CircuitBreaker(max_consecutive_losses=3)
    cb.record_trade(Decimal("-500"))
    cb.record_trade(Decimal("-500"))
    # A winning trade resets the counter
    cb.record_trade(Decimal("1000"))
    # Two more losses should not trip (counter reset to 0)
    cb.record_trade(Decimal("-500"))
    cb.record_trade(Decimal("-500"))
    assert cb.is_open is False


def test_record_trade_zero_pnl_neutral() -> None:
    cb = CircuitBreaker(max_consecutive_losses=2)
    cb.record_trade(Decimal("-500"))
    cb.record_trade(Decimal(0))  # neither increments nor resets
    cb.record_trade(Decimal("-500"))
    assert cb.is_open is True


def test_history_recorded_on_auto_trip() -> None:
    cb = CircuitBreaker(max_consecutive_losses=2)
    cb.record_trade(Decimal("-1"))
    cb.record_trade(Decimal("-1"))
    assert len(cb.trip_history) == 1
    assert cb.trip_history[0][1] == "CONSECUTIVE_LOSSES"


def test_reset_clears_consecutive_loss_counter() -> None:
    cb = CircuitBreaker(max_consecutive_losses=3)
    cb.record_trade(Decimal("-1"))
    cb.record_trade(Decimal("-1"))
    cb.record_trade(Decimal("-1"))
    assert cb.is_open is True
    cb.reset("MANUAL_RESET_CONFIRMED", 999)
    # Counter reset: next two losses should not re-trip immediately
    cb.record_trade(Decimal("-1"))
    cb.record_trade(Decimal("-1"))
    assert cb.is_open is False


def test_trip_history_is_immutable_tuple() -> None:
    cb = CircuitBreaker()
    cb.trip("X", 1)
    history = cb.trip_history
    assert isinstance(history, tuple)
