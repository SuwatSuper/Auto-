# Layer 2 — Orchestration (runtime/runtime_risk)
"""Risk settings, circuit breaker, and execution-mode control plane.

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from orchestration.runtime_base import _RuntimeBase

if TYPE_CHECKING:
    from orchestration.control import RiskSettings


class _RiskControlMixin(_RuntimeBase):
    _LIVE_TOKEN = "I_ACCEPT_REAL_MONEY_RISK"
    _BREAKER_RESET_TOKEN = "MANUAL_RESET_CONFIRMED"


    def _risk_equity_state(self) -> tuple[Decimal, Decimal, Decimal]:
        """Real (peak_equity, current_equity, daily_pnl) for the Risk agent's
        drawdown / daily-loss checks. Before any trade this is the honest
        no-movement baseline (equity == peak, pnl == 0), not a fabrication."""
        if self._treasury is not None and self._trader is not None:
            current = self._treasury.cash + self._trader.open_market_value()
            daily_pnl = self._treasury.realized_today + self._trader.unrealized_pnl()
            peak = self._peak_equity if self._peak_equity >= current else current
            return peak, current, daily_pnl
        return self._initial_capital, self._initial_capital, Decimal("0")

    def _win_rate(self) -> float | None:
        """Win rate of the rolling paper backtest run by the execution
        department over live prices (fees + slippage included). None until
        the first window completes — never a fabricated number."""
        agent = self.agents.get("execution_agent")
        raw = getattr(agent, "last_win_rate", None) if agent is not None else None
        if raw is None:
            return None
        try:
            return float(Decimal(str(raw)))
        except InvalidOperation:
            return None

    def _risk_gate(self) -> object | None:
        return self.agents.get("risk_gate")

    def _current_risk_settings(self) -> RiskSettings:
        """Build a RiskSettings snapshot from the live objects."""
        from orchestration.control import RiskSettings  # noqa: PLC0415

        tp = self._trade_params
        br = self._circuit_breaker
        gate = self._risk_gate()
        daily = (
            self._treasury.limits.max_daily_loss_pct
            if self._treasury is not None
            else self._dec_setting("max_daily_loss_pct", "5")
        )
        return RiskSettings(
            risk_per_trade_pct=getattr(tp, "risk_per_trade_pct", Decimal("1")),
            stop_pct=getattr(tp, "stop_pct", Decimal("1")),
            take_profit_pct=getattr(tp, "take_profit_pct", Decimal("1.5")),
            max_daily_loss_pct=daily,
            max_consecutive_losses=(
                br.max_consecutive_losses if br is not None else 5
            ),
            max_open_positions=int(getattr(gate, "_max_open_positions", 1)),
            max_deployable_thb=self._max_deployable_thb,
            max_single_order_thb=self._max_single_order_thb,
            min_p_win=self._dec_setting("min_p_win", "0.55"),
        )

    def get_risk_settings(self) -> dict[str, str]:
        """Current live risk settings for the dashboard."""
        return self._current_risk_settings().as_str_dict()

    async def update_risk_settings(
        self, patch: dict[str, object]
    ) -> tuple[bool, dict[str, object]]:
        """Validate + apply risk settings live. Returns (ok, payload).

        On success the new values immediately affect the next trade (sizing,
        stop/TP), the daily-loss cap, the consecutive-loss breaker threshold,
        and the open-position cap. Settings are persisted to the state store.
        """
        from orchestration.control import validate_risk_settings  # noqa: PLC0415

        current = self._current_risk_settings()
        new, errors = validate_risk_settings(current, patch)
        if new is None:
            return False, {"errors": errors}

        # Apply to the live objects.
        tp = self._trade_params
        if tp is not None:
            tp.risk_per_trade_pct = new.risk_per_trade_pct  # type: ignore[attr-defined]
            tp.stop_pct = new.stop_pct  # type: ignore[attr-defined]
            tp.take_profit_pct = new.take_profit_pct  # type: ignore[attr-defined]
        if self._treasury is not None:
            from domain.portfolio.treasury import TreasuryLimits  # noqa: PLC0415

            self._treasury.update_limits(
                TreasuryLimits(
                    initial_capital=self._initial_capital,
                    survival_floor_pct=self._dec_setting("survival_floor_pct", "70"),
                    max_daily_loss_pct=new.max_daily_loss_pct,
                )
            )
        if self._circuit_breaker is not None:
            self._circuit_breaker.update_threshold(new.max_consecutive_losses)
        # Win-probability gate is operator-tunable live: update the setting the
        # entry gate reads AND the Timeline Analyst's own threshold/display.
        self.settings.min_p_win = str(new.min_p_win)  # type: ignore[attr-defined]
        if self._timeline is not None and hasattr(self._timeline, "set_min_p_win"):
            self._timeline.set_min_p_win(new.min_p_win)
        gate = self._risk_gate()
        if gate is not None and hasattr(gate, "set_max_open_positions"):
            gate.set_max_open_positions(new.max_open_positions)
        self._max_deployable_thb = new.max_deployable_thb
        self._max_single_order_thb = new.max_single_order_thb
        # Keep the paper sizing cap in lockstep with the live order cap so a
        # real order and its paper mirror size identically.
        if tp is not None:
            tp.max_order_thb = new.max_single_order_thb  # type: ignore[attr-defined]

        await self._persist_controls(new.as_str_dict())
        self._record_control("risk_settings_updated", dict(patch))
        return True, {"settings": new.as_str_dict()}

    def update_trailing_stop(self, new_stop: object) -> bool:
        """Let the Trailing-Stop agent ratchet the live position's protective
        stop UP (lock profit). Real effect — not advisory. Returns True if
        the stop moved. Disabled via trailing_stop_enabled=false."""
        if self._trader is None:
            return False
        if not bool(getattr(self.settings, "trailing_stop_enabled", True)):
            return False
        try:
            stop = Decimal(str(new_stop))
        except (InvalidOperation, ValueError, TypeError):
            return False
        return self._trader.set_trail_stop(stop)

    def apply_kelly_risk(self, suggested_pct: object) -> bool:
        """Let the Kelly sizer drive the live per-trade risk %, clamped to a
        safe band [0.25 .. kelly_max_risk_pct]. Real effect on the NEXT entry.
        Disabled via kelly_sizing_enabled=false. Returns True if applied."""
        tp = self._trade_params
        if tp is None or not bool(getattr(self.settings, "kelly_sizing_enabled", True)):
            return False
        try:
            val = Decimal(str(suggested_pct))
        except (InvalidOperation, ValueError, TypeError):
            return False
        lo = Decimal("0.25")
        hi = self._dec_setting("kelly_max_risk_pct", "2.0")
        if hi < lo:
            hi = lo
        clamped = max(lo, min(hi, val))
        tp.risk_per_trade_pct = clamped  # type: ignore[attr-defined]
        return True

    def trip_breaker(self, reason: str = "MANUAL") -> dict[str, object]:
        """Manually open the circuit breaker (halts trading via the risk gate)."""
        if self._circuit_breaker is None:
            return {"ok": False, "error": "no breaker"}
        self._circuit_breaker.trip(reason or "MANUAL", int(time.time()))
        self._record_control("breaker_trip", {"reason": reason})
        self._schedule_alert(f"🛑 Circuit breaker tripped: {reason}", "critical")
        return {"ok": True, "is_open": True}

    def reset_breaker(self, token: str) -> dict[str, object]:
        """Close the breaker — requires the confirmation token."""
        if self._circuit_breaker is None:
            return {"ok": False, "error": "no breaker"}
        ok = self._circuit_breaker.reset(token, int(time.time()))
        if ok:
            self._record_control("breaker_reset", {})
        return {"ok": ok, "is_open": self._circuit_breaker.is_open}

    def _live_gate_checklist(self) -> dict[str, bool]:
        """Return each live gate's pass/fail state (truthful, no guesswork)."""
        from pathlib import Path  # noqa: PLC0415

        engine = str(getattr(self.settings, "execution_engine", "paper"))
        confirm = str(getattr(self.settings, "live_trading_confirm", ""))
        kill = Path("data/KILL_SWITCH").exists()
        breaker_open = bool(self._circuit_breaker and self._circuit_breaker.is_open)
        return {
            "engine_live": engine == "live",
            "confirm_token": confirm == self._LIVE_TOKEN,
            "kill_switch_clear": not kill,
            "breaker_closed": not breaker_open,
        }

    def get_execution_mode(self) -> dict[str, object]:
        """Current execution mode + the 4-gate checklist."""
        gates = self._live_gate_checklist()
        return {
            "mode": str(getattr(self.settings, "execution_engine", "paper")),
            "gates": gates,
            "all_gates_open": all(gates.values()),
        }

    def set_execution_mode(
        self, mode: str, confirm: str = ""
    ) -> tuple[bool, dict[str, object]]:
        """Switch paper<->live. Live requires the confirm token AND the other
        gates (no kill switch, breaker closed). Paper always allowed."""
        if mode == "paper":
            self.settings.execution_engine = "paper"  # type: ignore[attr-defined]
            self.settings.live_trading_confirm = ""  # type: ignore[attr-defined]
            self._record_control("execution_mode", {"mode": "paper"})
            return True, self.get_execution_mode()
        if mode != "live":
            return False, {"error": f"unknown mode {mode!r} (use 'paper' or 'live')"}
        if confirm != self._LIVE_TOKEN:
            return False, {
                "error": "live requires the confirmation token",
                "required_token": self._LIVE_TOKEN,
            }
        from pathlib import Path  # noqa: PLC0415

        if Path("data/KILL_SWITCH").exists():
            return False, {"error": "KILL_SWITCH file present — remove it first"}
        if self._circuit_breaker is not None and self._circuit_breaker.is_open:
            return False, {"error": "circuit breaker is OPEN — reset it first"}
        # Real-money guard: never arm live with an unbounded order size. Require
        # a per-order THB cap so the first live orders are bounded even if the
        # experiment-mode loss limits are still wide open.
        if self._max_single_order_thb <= 0:
            return False, {
                "error": (
                    "set a per-order cap first: max_single_order_thb must be > 0 "
                    "before going live (protects against an unbounded first order)"
                ),
                "field": "max_single_order_thb",
            }
        # A cap below the exchange minimum would make every live order bounce.
        min_thb = self._dec_setting("bitkub_min_order_thb", "10")
        if 0 < self._max_single_order_thb < min_thb:
            return False, {
                "error": (
                    f"per-order cap {self._max_single_order_thb} is below Bitkub's "
                    f"minimum order ({min_thb} THB) — raise it or orders will bounce"
                ),
                "field": "max_single_order_thb",
            }
        self.settings.execution_engine = "live"  # type: ignore[attr-defined]
        self.settings.live_trading_confirm = self._LIVE_TOKEN  # type: ignore[attr-defined]
        self._record_control("execution_mode", {"mode": "live"})
        return True, self.get_execution_mode()

    def control_audit(self, limit: int = 100) -> list[dict[str, object]]:
        """Recent operator control actions (who/what/when)."""
        return self._control_audit[-max(1, min(limit, 1000)):]

    def _record_control(self, action: str, detail: dict[str, object]) -> None:
        self._control_audit.append(
            {"ts_ms": int(time.time() * 1000), "action": action, "detail": detail}
        )
        if len(self._control_audit) > 2000:
            self._control_audit = self._control_audit[-2000:]
        self.logger.info("control.action", action=action, detail=detail)
