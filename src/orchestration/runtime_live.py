# Layer 2 — Orchestration (runtime/runtime_live)
"""Live trading: manual orders, live close, order building, account wiring.

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

import contextlib
from decimal import Decimal, InvalidOperation
from typing import cast

from domain.portfolio.treasury import worst_case_loss
from orchestration.ports.balance_source import BalanceSource
from orchestration.runtime_base import _RuntimeBase


class _LiveTradingMixin(_RuntimeBase):

    async def manual_order(
        self, side: str, price: object | None = None
    ) -> tuple[bool, dict[str, object]]:
        """Operator BUY / SELL(=CLOSE). In paper mode this changes the REAL
        paper portfolio; live routing remains gated. Respects breaker + cash."""
        if self._trader is None:
            return False, {"error": "runtime not started"}
        if self._circuit_breaker is not None and self._circuit_breaker.is_open:
            return False, {"error": "circuit breaker is OPEN"}
        px: Decimal | None = None
        if price is not None:
            try:
                px = Decimal(str(price))
            except (InvalidOperation, ValueError):
                return False, {"error": f"bad price {price!r}"}
            # Decimal("NaN")/Decimal("Infinity") parse OK but crash comparisons.
            if not px.is_finite() or px <= 0:
                return False, {"error": f"bad price {price!r}"}
        side_u = str(side).upper()
        if side_u == "BUY":
            # In live-armed mode a manual BUY fires a REAL bid first; the paper
            # position is then marked live-backed so its exits close the real
            # position too. Manual orders bypass the p_win gate (operator override).
            placed_live = await self._place_manual_live_bid(px)
            ok, msg = await self._trader.manual_buy(px, is_live=placed_live)
            if placed_live and ok:
                msg = f"{msg} (ส่งคำสั่งจริงบน Bitkub แล้ว)"
        elif side_u in ("SELL", "CLOSE"):
            # manual_close → _close(MANUAL) → live_close_fn closes the real
            # position when it was live-backed.
            ok, msg = await self._trader.manual_close(px)
        else:
            return False, {"error": f"unknown side {side!r} (use BUY/SELL)"}
        self._record_control("manual_order", {"side": side_u, "result": msg})
        if ok:
            self._schedule_alert(f"📋 Manual {side_u}: {msg}", "info")
        return ok, {"message": msg, "positions": self._trader.open_positions()}

    async def _place_manual_live_bid(self, px: Decimal | None) -> bool:
        """Place a REAL bid for an operator BUY when live orders are armed and
        no position is open. Returns True only if the real order was placed."""
        if self._trader is None or self._trade_params is None:
            return False
        if self._trader.position is not None or not self._live_orders_armed():
            return False
        if px is not None:
            self._trader.mark_price = px  # ensure sizing uses the operator price
        symbol = str(getattr(self._trade_params, "symbol", "THB_BTC"))
        spec = self._build_live_order({"signal": "BUY", "symbol": symbol})
        if not spec:
            return False
        gate = self.agents.get("risk_gate")
        gw = getattr(gate, "_rest_gateway", None) if gate is not None else None
        if gw is None or not hasattr(gw, "place_bid"):
            return False
        try:
            await gw.place_bid(
                spec["symbol"], spec["amount"], spec["rate"], spec.get("typ", "market")
            )
            self.logger.info("runtime.manual_live_bid", amount=spec["amount"])
            return True
        except Exception:
            self.logger.error("runtime.manual_live_bid_failed", exc_info=True)
            return False

    async def close_all(self) -> dict[str, object]:
        """Flatten all open paper positions (operator action)."""
        if self._trader is None:
            return {"ok": False, "error": "runtime not started"}
        from domain.trading.paper import ExitReason  # noqa: PLC0415

        await self._trader.flatten(ExitReason.MANUAL)
        self._record_control("close_all", {})
        return {"ok": True, "positions": self._trader.open_positions()}

    def _roll_trade_day(self) -> None:
        today = self._treasury.day_key if self._treasury is not None else ""
        if today != self._trades_day_key:
            self._trades_day_key = today
            self._entries_baseline = self._trader.entries_opened if self._trader is not None else 0

    def trades_today(self) -> int:
        cur = self._trader.entries_opened if self._trader is not None else 0
        return max(0, cur - self._entries_baseline)

    def daily_profit_pct(self) -> Decimal:
        if self._treasury is None or self._initial_capital <= 0:
            return Decimal("0")
        return (self._treasury.realized_today / self._initial_capital * Decimal("100"))

    def _trade_budget(self) -> bool:
        """True while a new entry is allowed today (trade-count quota + optional
        profit-target lock). Daily LOSS halting is owned by the treasury."""
        self._roll_trade_day()
        if self._max_trades_per_day > 0 and self.trades_today() >= self._max_trades_per_day:
            return False
        target_locked = (
            self._stop_at_daily_target
            and self._target_daily_profit_pct > 0
            and self.daily_profit_pct() >= self._target_daily_profit_pct
        )
        return not target_locked  # opt-in: halt new entries once target reached

    def _entry_gate(self, data: dict[str, object]) -> tuple[bool, list[str]]:
        """Confluence + win-probability gate for a proposed BUY entry.
        Returns (approved, reason_codes). Honest: p_win is the Timeline Analyst's
        MEASURED historical win rate, not a promise."""
        if not self._entry_gate_enabled:
            return True, []
        from domain.strategy.base import SignalAction  # noqa: PLC0415
        from domain.strategy.confluence import (  # noqa: PLC0415
            EntryInputs,
            GateParams,
            evaluate_entry,
        )

        tl = self._timeline
        p_win = Decimal(str(getattr(tl, "p_win", "0"))) if tl is not None else Decimal("0")
        samples = int(getattr(tl, "p_win_samples", 0)) if tl is not None else 0
        regime = str(getattr(tl, "regime", "RANGE")) if tl is not None else "RANGE"
        try:
            sentiment = Decimal(str(self.last_news.get("score", "0")))
        except (InvalidOperation, ValueError, TypeError):
            sentiment = Decimal("0")

        inputs = EntryInputs(
            signal_action=SignalAction.BUY,
            signal_confidence=Decimal("1"),  # already cleared Supreme consensus
            regime=regime,
            sentiment_score=sentiment,
            p_win=p_win,
            p_win_samples=samples,
            trend_agree=(regime != "TREND_DOWN"),
        )
        params = GateParams(
            min_p_win=self._dec_setting("min_p_win", "0.55"),
            min_confidence=self._dec_setting("gate_min_confidence", "0.50"),
            min_samples=int(getattr(self.settings, "gate_min_samples", 8)),
            block_regime_mismatch=bool(getattr(self.settings, "gate_block_regime_mismatch", False)),
        )
        decision = evaluate_entry(inputs, params)
        reasons = [r.value for r in decision.reasons]
        for r in reasons:
            self._gate_block_reasons[r] = self._gate_block_reasons.get(r, 0) + 1
        return decision.approved, reasons

    async def _live_close(self, qty: object, rate: object) -> None:
        """Place a REAL closing ask for a protective exit (stop/TP/trailing/
        manual/emergency) on the live exchange. Called by the paper trader only
        for live-backed positions; no-ops unless live orders are armed so it is
        always safe to wire in paper mode."""
        if not self._live_orders_armed():
            return
        gate = self.agents.get("risk_gate")
        gw = getattr(gate, "_rest_gateway", None) if gate is not None else None
        if gw is None or not hasattr(gw, "place_ask"):
            return
        symbol = str(getattr(self._trade_params, "symbol", "THB_BTC")).lower()
        # C2: never ask for more coin than is REALLY held. A market BUY fills a
        # slightly different qty than the paper mirror (slippage), so cap the
        # closing ask to the real wallet BTC balance — otherwise Bitkub rejects
        # the over-sized ask and the position is left unhedged.
        sell_qty = Decimal(str(qty))
        real_btc = self._real_btc_balance()
        if real_btc is not None and 0 < real_btc < sell_qty:
            sell_qty = real_btc
        if sell_qty <= 0:
            return
        try:
            # market order: a protective stop must FILL even as price falls through.
            result = await gw.place_ask(symbol, str(sell_qty), str(rate), "market")
            self.logger.info("runtime.live_exit_order", qty=str(sell_qty), rate=str(rate),
                             order_id=(result.get("result", {}) or {}).get("id")
                             if isinstance(result, dict) else None)
        except Exception:
            self.logger.error("runtime.live_exit_failed", exc_info=True)
            self._schedule_alert(
                f"⚠️ ปิด position จริงไม่สำเร็จ (qty {sell_qty}) — ตรวจสอบบัญชี Bitkub ด่วน",
                "critical",
            )

    def _real_btc_balance(self) -> Decimal | None:
        """Real BTC available in the connected Bitkub wallet (from the last
        reconciliation poll), or None when unknown."""
        recon = self._reconciliation
        balances = dict(getattr(recon, "last_balances", {})) if recon is not None else {}
        for sym in ("BTC", "THB_BTC"):
            if sym in balances:
                try:
                    return Decimal(str(balances[sym]))
                except (InvalidOperation, ValueError):
                    return None
        return None

    def _build_live_order(self, data: dict[str, object]) -> dict[str, str] | None:
        """Turn an approved decision into a sized, capped live order spec.

        Uses the same sizing as the paper engine, then clamps the notional to
        ``max_single_order_thb`` (when set) as a hard safety cap for the first
        live orders. Returns {action: bid|ask, symbol, amount, rate} or None.
        """
        from domain.trading.paper import size_order, slip_buy  # noqa: PLC0415

        signal = str(data.get("signal", ""))
        symbol = str(data.get("symbol", "thb_btc")).lower()
        trader = self._trader
        tp = self._trade_params
        if trader is None or tp is None or self._treasury is None:
            return None
        mark = trader.mark_price
        if mark is None:
            return None

        if signal == "BUY":
            if trader.position is not None:
                return None  # single-position rule
            entry = slip_buy(mark, tp.slippage_bps)  # type: ignore[attr-defined]
            stop = entry * (Decimal("1") - tp.stop_pct / Decimal("100"))  # type: ignore[attr-defined]
            qty = size_order(
                cash=self._treasury.cash,
                entry_price=entry,
                stop_price=stop,
                risk_per_trade_pct=tp.risk_per_trade_pct,  # type: ignore[attr-defined]
                fee_bps=tp.fee_taker_bps,  # type: ignore[attr-defined]
                slippage_bps=Decimal("0"),
            )
            if qty <= 0:
                return None
            # Apply the per-order THB cap on QTY (not notional) so the real
            # order and its paper mirror — which caps qty identically — end up
            # the same size. No divergence when the cap is active.
            # B1: the effective cap can NEVER exceed the hard-coded ceiling, even
            # if _max_single_order_thb was set higher by a bug or direct mutation
            # — the real order is clamped at the point of spending real money.
            from orchestration.control import HARD_CAP_SINGLE_ORDER_THB  # noqa: PLC0415
            cap = self._max_single_order_thb
            if cap > 0:
                cap = min(cap, HARD_CAP_SINGLE_ORDER_THB)
                if entry > 0 and qty * entry > cap:
                    from decimal import ROUND_DOWN  # noqa: PLC0415
                    qty = (cap / entry).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
            if qty <= 0:
                return None
            notional = qty * mark
            # Bitkub rejects orders below its minimum notional — never send a
            # doomed order (it would silently fail on the exchange).
            min_thb = self._dec_setting("bitkub_min_order_thb", "10")
            if notional < min_thb:
                self.logger.warning(
                    "runtime.live_order_below_min", notional=str(notional), min_thb=str(min_thb)
                )
                return None
            # C1: gate the REAL order behind the treasury BEFORE placing it, so a
            # halted / underfunded / floor-breaching account never spends real
            # money and is never left with an untracked, unhedged live position.
            from domain.trading.paper import fee_for  # noqa: PLC0415
            entry_fee = fee_for(qty * entry, tp.fee_taker_bps)  # type: ignore[attr-defined]
            order_cost = qty * entry + entry_fee
            exit_fee_est = fee_for(qty * stop, tp.fee_taker_bps)  # type: ignore[attr-defined]
            worst = worst_case_loss(qty, entry, stop, entry_fee, exit_fee_est)
            if not self._treasury.would_approve(order_cost, worst, trader.open_market_value()):
                self.logger.warning("runtime.live_order_treasury_veto")
                return None
            return {
                "action": "bid",
                "symbol": symbol,
                "amount": str(notional.quantize(Decimal("0.01"))),
                "rate": str(mark),
                "typ": str(getattr(self.settings, "live_order_type", "market")),
            }

        if signal == "SELL":
            pos = trader.position
            if pos is None:
                return None  # nothing to sell/close
            return {
                "action": "ask",
                "symbol": symbol,
                "amount": str(pos.qty),
                "rate": str(mark),
                "typ": str(getattr(self.settings, "live_order_type", "market")),
            }
        return None

    def account_status(self) -> dict[str, object]:
        """Real-account connection status (never leaks the key)."""
        recon = self._reconciliation
        try:
            has_key = bool(
                getattr(self.settings, "bitkub_api_key", None)
                and self.settings.bitkub_api_key.get_secret_value()  # type: ignore[attr-defined]
            )
        except AttributeError:
            has_key = bool(getattr(self.settings, "bitkub_api_key", None))
        return {
            "has_key": has_key,
            "connected": self._rest_gateway is not None,
            "reconciled": bool(getattr(recon, "is_reconciled", False)) if recon else False,
            "balances": dict(getattr(recon, "last_balances", {})) if recon else {},
            "last_error": getattr(recon, "last_error", None) if recon else None,
        }

    async def connect_account(
        self,
        api_key: str,
        api_secret: str,
        *,
        balance_source: object | None = None,
        start_polling: bool = True,
    ) -> dict[str, object]:
        """Connect the REAL Bitkub account live: update credentials, build the
        gateway + reconciliation poller, persist to .env. No restart needed.
        balance_source can be injected for tests (avoids real network)."""
        if not api_key or not api_secret:
            return {"ok": False, "error": "api_key and api_secret are required"}
        from pydantic import SecretStr  # noqa: PLC0415

        self.settings.bitkub_api_key = SecretStr(api_key)  # type: ignore[attr-defined]
        self.settings.bitkub_api_secret = SecretStr(api_secret)  # type: ignore[attr-defined]

        await self._disconnect_account()

        if balance_source is None:
            from infrastructure.gateway.bitkub_balance import BitkubBalanceSource  # noqa: PLC0415
            from orchestration.agents.execution_agent import build_live_gateway  # noqa: PLC0415

            gateway = build_live_gateway(
                getattr(self.settings, "bitkub_api_key", None),
                getattr(self.settings, "bitkub_api_secret", None),
            )
            with contextlib.suppress(Exception):
                await gateway.__aenter__()  # type: ignore[attr-defined]
            self._rest_gateway = gateway
            balance_source = BitkubBalanceSource(gateway)
        else:
            self._rest_gateway = object()  # marker so status shows connected

        from orchestration.agents.reconciliation_agent import ReconciliationAgent  # noqa: PLC0415

        recon = ReconciliationAgent(
            self._ensure_bus(), cast(BalanceSource, balance_source), "reconciliation.v1",
            self.logger, poll_interval_s=60.0,
        )
        self._reconciliation = recon
        self.agents["reconciliation"] = recon
        # Keep the execution gate's live gateway in sync with the freshly
        # connected account (None-safe; only a real signed gateway can order).
        gate = self.agents.get("risk_gate")
        if gate is not None and hasattr(gate, "set_rest_gateway"):
            gw = self._rest_gateway if hasattr(self._rest_gateway, "place_bid") else None
            gate.set_rest_gateway(gw)

        # Immediately VERIFY by reading the real wallet once, so the Connect
        # response tells the truth: real balances on success, or the real
        # Bitkub error (bad key / no permission / IP not allowed) on failure.
        verified = False
        verify_error: str | None = None
        balances: dict[str, str] = {}
        try:
            raw = await balance_source.get_balance()  # type: ignore[attr-defined]
            balances = {k: str(v) for k, v in raw.items()}
            verified = True
        except Exception as exc:
            verify_error = str(exc)
        recon.set_state(reconciled=verified, error=verify_error, balances=balances)

        if start_polling:
            await self.start_agent("reconciliation")
        self._persist_credentials(api_key, api_secret)
        self._record_control("credentials_set", {"has_key": True, "verified": verified})
        if verified:
            self._schedule_alert("🔌 Bitkub account connected & wallet read OK", "info")
        else:
            self._schedule_alert(f"⚠️ Bitkub connected but wallet read failed: {verify_error}", "warning")
        return {
            "ok": True,
            "verified": verified,
            "error": verify_error,
            "balances": balances,
            **self.account_status(),
        }

    async def _disconnect_account(self) -> None:
        """Stop any existing reconciliation poller and close the gateway."""
        # Disable live order routing first — never leave the gate holding a
        # gateway that is about to be closed.
        gate = self.agents.get("risk_gate")
        if gate is not None and hasattr(gate, "set_rest_gateway"):
            gate.set_rest_gateway(None)
        if "reconciliation" in self.agents:
            with contextlib.suppress(Exception):
                await self.stop_agent("reconciliation")
            self.agents.pop("reconciliation", None)
        if self._rest_gateway is not None:
            exit_fn = getattr(self._rest_gateway, "__aexit__", None)
            if callable(exit_fn):
                with contextlib.suppress(Exception):
                    await exit_fn(None, None, None)
        self._rest_gateway = None
        self._reconciliation = None

    def _persist_credentials(self, api_key: str, api_secret: str) -> None:
        """Write the credentials into .env, preserving other lines."""
        from pathlib import Path  # noqa: PLC0415

        env = Path(".env")
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []

        def _set(field: str, value: str, src: list[str]) -> list[str]:
            prefix = field + "="
            out: list[str] = []
            found = False
            for ln in src:
                if ln.strip().startswith(prefix):
                    out.append(f"{field}={value}")
                    found = True
                else:
                    out.append(ln)
            if not found:
                out.append(f"{field}={value}")
            return out

        lines = _set("BITKUB_API_KEY", api_key, lines)
        lines = _set("BITKUB_API_SECRET", api_secret, lines)
        with contextlib.suppress(Exception):
            env.write_text("\n".join(lines) + "\n", encoding="utf-8")
