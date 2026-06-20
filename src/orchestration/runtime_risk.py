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
            max_trades_per_day=self._max_trades_per_day,
            adapt_after_trades=int(
                getattr(self.agents.get("market_analyst"), "_adapt_every", 8)
            ),
        )

    def get_risk_settings(self) -> dict[str, str]:
        """Current live risk settings for the dashboard."""
        return self._current_risk_settings().as_str_dict()

    async def update_risk_settings(
        self, patch: dict[str, object], *, from_restore: bool = False
    ) -> tuple[bool, dict[str, object]]:
        """Validate + apply risk settings live. Returns (ok, payload).

        On success the new values immediately affect the next trade (sizing,
        stop/TP), the daily-loss cap, the consecutive-loss breaker threshold,
        and the open-position cap. Settings are persisted to the state store.

        ``from_restore`` marks a machine-driven reload at startup (load_controls).
        A restored snapshot always carries ``risk_per_trade_pct``, so it must NOT
        be mistaken for an operator hand-setting the risk % (which disables the
        Kelly auto-sizer). On restore the Kelly toggle is left untouched (M9).
        """
        from orchestration.control import validate_risk_settings  # noqa: PLC0415

        current = self._current_risk_settings()
        new, errors = validate_risk_settings(current, patch)
        if new is None:
            return False, {"errors": errors}

        # Apply to the live objects.
        tp = self._trade_params
        if tp is not None:
            tp.risk_per_trade_pct = new.risk_per_trade_pct
            tp.stop_pct = new.stop_pct
            tp.take_profit_pct = new.take_profit_pct
        # Operator takes the wheel: when they SET risk %/trade by hand, the Kelly
        # auto-sizer must stop re-clamping it (it would otherwise pull any value
        # back into [0.25 .. kelly_max_risk_pct] on the next cycle, so a typed 10%
        # silently became ≤2% — the "ไม่ลิ้งกัน" the operator hit). Their exact %
        # now sticks. Re-enable Kelly from .env (KELLY_SIZING_ENABLED=true).
        # M9: skip this on a startup restore — a reloaded snapshot always carries
        # risk_per_trade_pct and would otherwise disable Kelly on every boot.
        if "risk_per_trade_pct" in patch and not from_restore:
            self.settings.kelly_sizing_enabled = False
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
        self.settings.min_p_win = str(new.min_p_win)
        if self._timeline is not None and hasattr(self._timeline, "set_min_p_win"):
            self._timeline.set_min_p_win(new.min_p_win)
        gate = self._risk_gate()
        if gate is not None and hasattr(gate, "set_max_open_positions"):
            gate.set_max_open_positions(new.max_open_positions)
        self._max_deployable_thb = new.max_deployable_thb
        self._max_single_order_thb = new.max_single_order_thb
        # Operator-controlled daily entry budget (0 = unlimited).
        self._max_trades_per_day = new.max_trades_per_day
        # Operator-controlled experience-before-self-tuning cadence.
        analyst = self.agents.get("market_analyst")
        if analyst is not None and hasattr(analyst, "set_adapt_every"):
            analyst.set_adapt_every(new.adapt_after_trades)
        # Keep the paper sizing cap in lockstep with the live order cap so a
        # real order and its paper mirror size identically.
        if tp is not None:
            tp.max_order_thb = new.max_single_order_thb

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
        tp.risk_per_trade_pct = clamped
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
            self.settings.execution_engine = "paper"
            self.settings.live_trading_confirm = ""
            self._persist_execution_mode("paper", "")
            self._record_control("execution_mode", {"mode": "paper"})
            return True, self.get_execution_mode()
        if mode != "live":
            return False, {"error": f"unknown mode {mode!r} (use 'paper' or 'live')"}
        if confirm != self._LIVE_TOKEN:
            return False, {
                "error": "live requires the confirmation token",
                "required_token": self._LIVE_TOKEN,
            }
        ok, err = self._live_arm_preconditions()
        if not ok:
            return False, err
        self.settings.execution_engine = "live"
        self.settings.live_trading_confirm = self._LIVE_TOKEN
        # Persist so the operator's choice survives a restart ('ตั้งครั้งเดียวจบ').
        # The kill-switch, per-order cap and breaker are still re-checked on every
        # live decision, so persisting the armed state does not bypass them.
        self._persist_execution_mode("live", self._LIVE_TOKEN)
        # Honesty: base the money figures + order sizing on the REAL THB wallet
        # so equity/cash/% reflect real money, not the paper ฿1,000 sandbox.
        self._seed_capital_from_real_balance()
        self._record_control("execution_mode", {"mode": "live"})
        return True, self.get_execution_mode()

    def _live_arm_preconditions(self) -> tuple[bool, dict[str, object]]:
        """All gates (besides the confirm token) that must hold to run live.

        Re-used both when the operator arms live AND when re-validating a
        persisted live flag on restart (H2), so a reboot can never come up armed
        with weaker invariants than the original arming required."""
        from pathlib import Path  # noqa: PLC0415

        if Path("data/KILL_SWITCH").exists():
            return False, {"error": "KILL_SWITCH file present — remove it first"}
        if self._circuit_breaker is not None and self._circuit_breaker.is_open:
            return False, {"error": "circuit breaker is OPEN — reset it first"}
        # Real-money guard: never arm live with an unbounded order size.
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
        # B1: never arm live above the hard-coded real-money ceiling.
        from orchestration.control import HARD_CAP_SINGLE_ORDER_THB  # noqa: PLC0415
        if self._max_single_order_thb > HARD_CAP_SINGLE_ORDER_THB:
            return False, {
                "error": (
                    f"per-order cap {self._max_single_order_thb} exceeds the hard "
                    f"ceiling {HARD_CAP_SINGLE_ORDER_THB} THB enforced in code — "
                    "lower it before going live"
                ),
                "field": "max_single_order_thb",
            }
        # M1: never arm live with the automatic capital backstops disabled. The
        # shipped experiment-mode defaults (breaker=0 UNLIMITED, daily-loss=100%)
        # leave only the survival floor — require real backstops so a losing
        # streak / bad day actually halts trading.
        breaker_thr = (
            self._circuit_breaker.max_consecutive_losses
            if self._circuit_breaker is not None
            else 0
        )
        if breaker_thr <= 0:
            return False, {
                "error": (
                    "set a consecutive-loss limit first: max_consecutive_losses "
                    "must be > 0 before going live (0 = unlimited disables the "
                    "circuit breaker)"
                ),
                "field": "max_consecutive_losses",
            }
        daily_loss = (
            self._treasury.limits.max_daily_loss_pct
            if self._treasury is not None
            else self._dec_setting("max_daily_loss_pct", "5")
        )
        if daily_loss >= Decimal("100"):
            return False, {
                "error": (
                    "tighten the daily-loss cap first: max_daily_loss_pct must be "
                    "< 100 before going live (100% disables the daily-loss halt)"
                ),
                "field": "max_daily_loss_pct",
            }
        return True, {}

    def _revalidate_persisted_execution_mode(self) -> None:
        """On startup, never silently boot ARMED for live from a persisted .env
        flag without re-checking the arm-time invariants (H2).

        If .env says live, re-run the full precondition chain. If anything fails
        (cap unset, breaker open, backstops disabled, kill switch present), drop
        to paper and alert — the operator must consciously re-arm. A reboot is
        thus never a back-door to live trading with weaker rules than arming."""
        if str(getattr(self.settings, "execution_engine", "paper")) != "live":
            return
        ok, err = self._live_arm_preconditions()
        if ok:
            self.logger.info("runtime.live_mode_restored_from_env")
            return
        self.settings.execution_engine = "paper"
        self.settings.live_trading_confirm = ""
        self._persist_execution_mode("paper", "")
        self.logger.warning(
            "runtime.live_disarmed_on_restart", reason=err.get("error")
        )
        self._schedule_alert(
            "⚠️ รีสตาร์ท: ปิด live อัตโนมัติเพื่อความปลอดภัย "
            f"({err.get('error')}) — ตั้งค่าให้ครบแล้วกดเปิด live ใหม่",
            "critical",
        )

    def _seed_capital_from_real_balance(self) -> None:
        """When arming live with a connected account, set the trading capital to
        the real available THB so equity/cash/sizing track real money. No-op if
        the wallet hasn't been read, or a position is open (avoids resetting cash
        mid-trade)."""
        recon = self._reconciliation
        if recon is None or self._treasury is None or self._trader is None:
            return
        if self._trader.position is not None:
            return
        balances = dict(getattr(recon, "last_balances", {}))
        if "THB" not in balances:  # wallet not read yet — keep current base
            return
        try:
            thb = Decimal(str(balances["THB"]))
        except (InvalidOperation, ValueError):
            return
        if not thb.is_finite() or thb < 0:
            return
        self._initial_capital = thb
        self._peak_equity = thb
        self._treasury.set_capital(thb)
        if bool(getattr(self.settings, "persist_state", True)):
            self._persist_capital(thb)
        self._record_control("capital_synced_from_wallet", {"thb": str(thb)})

    def set_initial_capital(self, raw: object) -> tuple[bool, dict[str, object]]:
        """T2: set the paper starting capital (money base) live, re-fund the
        treasury, and persist to .env so it survives a restart."""
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return False, {"error": f"initial_capital: not a number ({raw!r})"}
        if value <= 0:
            return False, {"error": "initial_capital must be > 0"}
        # Refuse while a position is open: set_capital re-funds cash to the new
        # base while the reserved cash + open position still exist, which would
        # double-count equity (cash + open_market_value) and break the
        # cash == initial + realized invariant. Close first, then re-base.
        if self._trader is not None and self._trader.position is not None:
            return False, {"error": "close the open position before changing capital"}
        self._initial_capital = value
        self._peak_equity = value
        if self._treasury is not None:
            self._treasury.set_capital(value)
        self._persist_capital(value)
        self._record_control("initial_capital", {"value": str(value)})
        return True, {"initial_capital": str(value)}

    def _persist_capital(self, value: Decimal) -> None:
        """Write INITIAL_CAPITAL into .env, preserving other lines."""
        self._persist_env_setting("INITIAL_CAPITAL", str(value))

    def _persist_execution_mode(self, engine: str, confirm: str) -> None:
        """Persist EXECUTION_ENGINE + LIVE_TRADING_CONFIRM to .env (production
        only). Gated on persist_state so ephemeral test runtimes never write .env."""
        if not bool(getattr(self.settings, "persist_state", True)):
            return
        self._persist_env_setting("EXECUTION_ENGINE", engine)
        self._persist_env_setting("LIVE_TRADING_CONFIRM", confirm)

    def _persist_env_setting(self, field: str, value: str) -> None:
        """Upsert ``FIELD=value`` into .env, preserving other lines.

        Writes ATOMICALLY (tmp + fsync + os.replace) so a crash mid-write can't
        truncate/corrupt .env and lose credentials or the execution-mode flag
        (H7), and locks the file to owner-only since it holds the Bitkub secret
        and dashboard key (M8)."""
        import contextlib  # noqa: PLC0415
        import os  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        env = Path(".env")
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        out: list[str] = []
        found = False
        prefix = field + "="
        for ln in lines:
            if ln.strip().startswith(prefix):
                out.append(f"{field}={value}")
                found = True
            else:
                out.append(ln)
        if not found:
            out.append(f"{field}={value}")
        data = "\n".join(out) + "\n"
        try:
            tmp = env.with_name(env.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, env)
            # M8: .env holds the Bitkub secret + dashboard key — owner-only.
            with contextlib.suppress(OSError):
                os.chmod(env, 0o600)
        except OSError:
            # A failed write means the choice won't survive restart — surface it
            # instead of silently swallowing (the in-memory state is still set).
            self.logger.warning("runtime.env_persist_failed", field=field, exc_info=True)

    def set_daily_target(self, raw: object) -> tuple[bool, dict[str, object]]:
        """Phase 3: set the daily profit target % live (0..100), persisted."""
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return False, {"error": f"daily target: not a number ({raw!r})"}
        if value < 0 or value > 100:
            return False, {"error": "daily_profit_target_pct must be 0..100"}
        self._target_daily_profit_pct = value
        self._persist_env_setting("TARGET_DAILY_PROFIT_PCT", str(value))
        self._record_control("daily_target", {"target_pct": str(value)})
        return True, {"target_profit_pct": str(value)}

    def kill_switch_on(self) -> bool:
        """T4: True when the data/KILL_SWITCH file is present (blocks live)."""
        from pathlib import Path  # noqa: PLC0415

        return Path("data/KILL_SWITCH").exists()

    def set_kill_switch(self, on: bool) -> dict[str, object]:
        """T4: create/remove data/KILL_SWITCH — the hardest stop, which blocks
        arming live across restarts (checked in the live-gate checklist)."""
        from pathlib import Path  # noqa: PLC0415

        p = Path("data/KILL_SWITCH")
        if on:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("KILL_SWITCH active — live trading blocked\n", encoding="utf-8")
        else:
            p.unlink(missing_ok=True)
        self._record_control("kill_switch", {"on": on})
        return {"on": self.kill_switch_on()}

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
