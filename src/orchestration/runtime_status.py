# Layer 2 — Orchestration (runtime/runtime_status)
"""Status / reporting / learning-board surface for PipelineRuntime.

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

import time
from decimal import Decimal

from domain.shared.money import quantize_price
from orchestration.agents.learning import Learner, blended_score, reliability_score
from orchestration.runtime_base import AgentLike, _RuntimeBase


class _StatusMixin(_RuntimeBase):
    _EXP_CAP = 5000  # max agent skill (EXP) — agents level up from real work

    # Per-agent "learns from mistakes / can improve" cards for the dashboard
    # learning board (honest, specific descriptions per agent).
    _LEARNING_CARDS: dict[str, tuple[str, str]] = {
        "market_analyst": ("สัญญาณ EMA-cross ที่ทายผิดทิศ (เกรดกับราคาจริง)",
                           "เพิ่มเงื่อนไขยืนยัน gap EMA เมื่อแพ้บ่อย / ผ่อนเมื่อแม่น"),
        "news_intelligence": ("ข่าวที่ให้ sentiment ผิดทาง",
                             "ถ่วงน้ำหนักแหล่งข่าวที่แม่นกว่า (ขยาย feed)"),
        "risk_management": ("ออเดอร์ที่ปล่อยผ่านแล้วชนลิมิต",
                           "ปรับเพดานความเสี่ยง/exposure อัตโนมัติ"),
        "probability_lab": ("ค่าความน่าจะเป็น RSI ที่ทายผิด",
                           "ปรับช่วง RSI/threshold ที่ใช้คำนวณ"),
        "research_dept": ("สถิติย้อนหลังที่คลาดเคลื่อนจากของจริง",
                         "ขยายหน้าต่างข้อมูล/ความถี่ rolling"),
        "execution_agent": ("ผล backtest หมุนที่ขาดทุน",
                           "ปรับโมเดล fee/slippage ให้ตรงตลาดจริง"),
        "supreme_commander": ("การตัดสินใจที่สวนเสียงส่วนใหญ่แล้วผิด",
                             "ปรับเกณฑ์ consensus (จำนวนโหวต/กรอบเวลา)"),
        "risk_gate": ("ออเดอร์ที่โดน veto / โดนเกต p_win",
                     "ปรับ rate-limit + เกณฑ์ win-probability"),
        "treasury": ("การขาดทุนที่ทะลุเพดานรายวัน",
                    "ปรับ survival-floor / daily-loss limit"),
        "paper_trader": ("ไม้ที่โดน stop-loss",
                        "ปรับ stop / take-profit / trailing"),
        "ceo": ("เหตุการณ์เสี่ยงที่ควรเตือนแต่พลาด",
               "ปรับเกณฑ์การรายงาน/แจ้งเตือน"),
        "volatility_oracle": ("การพยากรณ์ squeeze/ระเบิดที่พลาด",
                             "ปรับ threshold ความผันผวน"),
        "trend_follower": ("เทรนด์หลอก (สัญญาณ EMA ผิด)",
                          "เพิ่ม gap ยืนยัน EMA จากผลแพ้/ชนะจริง"),
        "mean_reversion": ("การ fade ที่ผิด (ราคาไม่เด้งกลับ)",
                          "ปรับ RSI oversold/overbought จากผลจริง"),
        "breakout_specialist": ("เบรกหลอก (false breakout)",
                               "ขยาย/ลดกรอบ Donchian N จากผลจริง"),
        "black_swan_detector": ("การจับช็อกราคาช้า/พลาด",
                               "ปรับ threshold %การเคลื่อนไหว 60 วิ"),
        "drawdown_guardian": ("การสั่งหยุดเทรดช้าเกินไป",
                             "ปรับเพดาน drawdown รายวัน"),
        "position_sizer": ("ขนาดไม้ที่ใหญ่/เล็กเกินจาก Kelly",
                          "ปรับสูตร Kelly จาก win-rate จริง"),
        "trailing_stop": ("การล็อกกำไรช้าไป (คืนกำไร)",
                         "ปรับ %trailing ให้ตามกำไรจริง"),
        "profit_sweeper": ("จังหวะกวาดกำไรที่พลาด",
                          "ปรับสัดส่วนกวาดกำไรเข้าคลัง"),
        "fee_optimizer": ("การเลือก maker/taker ที่จ่ายแพง",
                         "ปรับกลยุทธ์ลดค่าธรรมเนียม"),
        "latency_pinger": ("ช่วง latency พุ่งที่ตอบสนองช้า",
                          "ปรับ threshold ชะลอการยิงออเดอร์"),
        "api_monitor": ("ช่วงฟีด/บัญชีหลุดที่จับช้า",
                       "ปรับความถี่/เกณฑ์การตรวจสอบ"),
        "dashboard_synth": ("KPI สรุปที่คลาดเคลื่อน",
                           "ปรับการกลั่น KPI รายวัน"),
        "tax_clerk": ("รายการ PnL ที่ตกหล่น",
                     "ปรับการจัดหมวดเพื่อภาษี"),
        "garbage_collector": ("รอบ GC ที่คืนหน่วยความจำได้น้อย",
                             "ปรับความถี่/เกณฑ์การเก็บกวาดหน่วยความจำ"),
    }



    def _task_alive(self, name: str) -> bool:
        task = self.agent_tasks.get(name)
        return task is not None and not task.done()

    def _agent_status(self, name: str, agent: AgentLike) -> dict[str, object]:
        """Generic, typed status view over any AgentLike."""
        stale_ms = int(getattr(self.settings, "heartbeat_stale_ms", 5000))
        now_ms = int(time.time() * 1000)
        alive = agent.running and self._task_alive(name)
        beat = agent.last_beat_ms
        stale = bool(alive and beat > 0 and (now_ms - beat) > stale_ms)
        status: dict[str, object] = {
            "name": name,
            "running": alive,
            "claimed_running": agent.running,
            "last_beat_ms": beat,
            "stale": stale,
            "crashed": bool(agent.running and not self._task_alive(name)),
            "crash_reason": self.crashed_agents.get(name),
            "restarts": self.restart_counts.get(name, 0),
            "msg_count": agent.msg_count,
        }
        parse_failures = getattr(agent, "parse_failures", None)
        if isinstance(parse_failures, int):
            status["parse_failures"] = parse_failures
        signal_count = getattr(agent, "signal_count", None)
        if isinstance(signal_count, int):
            status["signal_count"] = signal_count
        decision_count = getattr(agent, "decision_count", None)
        if isinstance(decision_count, int):
            status["decision_count"] = decision_count
        rejected_count = getattr(agent, "rejected_count", None)
        if isinstance(rejected_count, int):
            status["rejected_count"] = rejected_count

        # Human-readable detail (new agents expose .detail; others fall back).
        detail = getattr(agent, "detail", "")
        if isinstance(detail, str) and detail:
            status["detail"] = detail

        # ── EXP / level (skill) — earned from REAL work, hard-capped at 5000 ──
        sig = signal_count if isinstance(signal_count, int) else 0
        dec = decision_count if isinstance(decision_count, int) else 0
        rej = rejected_count if isinstance(rejected_count, int) else 0
        restarts = self.restart_counts.get(name, 0)
        raw_exp = agent.msg_count + sig * 15 + dec * 20 + rej * 10
        exp = max(0, min(self._EXP_CAP, raw_exp - restarts * 50))
        level = min(50, 1 + exp // 100)
        ranks = ["Rookie", "Skilled", "Expert", "Master", "Grandmaster", "Legendary"]
        rank = ranks[min(len(ranks) - 1, level // 10)]
        status["exp"] = exp
        status["exp_max"] = self._EXP_CAP
        status["level"] = level
        status["rank"] = rank

        # ── Self-improvement view: daily score + REAL accuracy ──
        learner = self._learner_for(name, agent)
        learner.roll_day()
        reliability = reliability_score(
            running=alive, stale=stale,
            crashed=bool(agent.running and not self._task_alive(name)),
            restarts=restarts, msg_count=agent.msg_count,
        )
        learner.score = round(blended_score(reliability, learner), 1)
        status["score"] = learner.score
        status["score_kind"] = learner.kind
        hr = learner.hit_rate()
        status["hit_rate"] = round(hr * 100, 1) if hr is not None else None
        status["resolved"] = learner.resolved
        status["adapt_count"] = learner.adapt_count
        # Learning board: what this agent learns from mistakes + can improve,
        # with the real recent losses and parameter changes it made.
        status.update(self._learning_card(name, agent, learner))
        return status

    def _learning_card(self, name: str, agent: AgentLike, learner: Learner) -> dict[str, object]:
        """What this agent learns from its mistakes + what it can improve, with
        REAL recent losing outcomes and the parameter changes it made."""
        lf = getattr(agent, "learns_from", None)
        ci = getattr(agent, "can_improve", None)
        learns_from = lf() if callable(lf) else None
        can_improve = ci() if callable(ci) else None
        if learns_from is None or can_improve is None:
            default = self._LEARNING_CARDS.get(
                name, ("ผลการทำงานจริงเทียบกับสิ่งที่คาด", "ปรับพารามิเตอร์จากสถิติจริง")
            )
            learns_from = learns_from or default[0]
            can_improve = can_improve or default[1]
        return {
            "learns_from": learns_from,
            "can_improve": can_improve,
            "recent_mistakes": learner.recent_mistakes(5),
            "recent_improvements": learner.recent_improvements(5),
        }

    def _learner_for(self, name: str, agent: AgentLike) -> Learner:
        """The agent's own Learner if it has one (extended agents), else a
        runtime-side reliability learner created on demand."""
        own = getattr(agent, "learner", None)
        if isinstance(own, Learner):
            return own
        if name not in self._learners:
            self._learners[name] = Learner(name, "reliability")
        return self._learners[name]

    def learning_overview(self, limit: int = 40) -> dict[str, object]:
        """Leaderboard + merged real-time learning feed across all agents.

        Every entry is a REAL event with a real timestamp — nothing fabricated.
        """
        rows: list[dict[str, object]] = []
        feed: list[dict[str, object]] = []
        for name, agent in self.agents.items():
            learner = self._learner_for(name, agent)
            hr = learner.hit_rate()
            card = self._learning_card(name, agent, learner)
            rows.append({
                "name": name,
                "score": learner.score,
                "kind": learner.kind,
                "hit_rate": round(hr * 100, 1) if hr is not None else None,
                "resolved": learner.resolved,
                "today_resolved": learner.today_resolved,
                "adapt_count": learner.adapt_count,
                **card,
            })
            for entry in learner.recent(limit):
                e = dict(entry)
                e["agent"] = name
                feed.append(e)
        rows.sort(key=lambda r: (r["score"] if isinstance(r["score"], int | float) else 0), reverse=True)
        feed.sort(key=lambda e: v if isinstance(v := e.get("ts_ms", 0), int) else 0, reverse=True)
        return {
            "ts_ms": int(time.time() * 1000),
            "llm_critic": "disabled (no API key) — scores are statistical, not LLM",
            "leaderboard": rows,
            "feed": feed[:limit],
        }

    def status(self) -> dict[str, object]:
        """Return current runtime status for the dashboard."""
        uptime_sec = int((time.time() * 1000 - self.start_time_ms) / 1000)
        window = list(self.msg_count_window)
        msg_per_sec = round(sum(window) / max(len(window), 1), 1)

        if self._treasury is not None and self._trader is not None:
            cash = self._treasury.cash
            equity = cash + self._trader.open_market_value()
            realized_today = self._treasury.realized_today
            pnl_today_dec = realized_today + self._trader.unrealized_pnl()
            positions = self._trader.open_positions()
            wins, losses = self._treasury.wins, self._treasury.losses
            trades_closed = self._trader.trades_closed
            halted = self._treasury.halted
            win_rate = self._treasury.win_rate()
        else:
            cash = equity = self._initial_capital
            realized_today = pnl_today_dec = Decimal("0")
            positions = wins = losses = trades_closed = 0
            halted = False
            win_rate = None
        if equity > self._peak_equity:
            self._peak_equity = equity
        drawdown_pct = (
            float((self._peak_equity - equity) / self._peak_equity * 100)
            if self._peak_equity > 0
            else 0.0
        )
        daily_loss_pct = (
            float(-realized_today / self._initial_capital * 100)
            if realized_today < 0
            else 0.0
        )

        recon = self._reconciliation
        account_connected = self._rest_gateway is not None
        reconciled = bool(getattr(recon, "is_reconciled", False)) if recon is not None else False
        real_balances = dict(getattr(recon, "last_balances", {})) if recon is not None else {}

        # p50/p95 latency from rolling window (real samples, never estimated)
        samples = sorted(self._latency_samples) if self._latency_samples else []
        p50_ms = samples[len(samples) // 2] if samples else 0
        p95_ms = samples[max(0, int(len(samples) * 0.95) - 1)] if len(samples) > 1 else (samples[0] if samples else 0)

        # Real portfolio (mark at latest price) — no fabricated values
        portfolio: list[dict[str, object]] = (
            self._trader.get_portfolio() if self._trader is not None else []
        )

        # Wallet value: sum bitkub_balances at real prices when available
        wallet_thb = self._compute_wallet_value_thb(real_balances)

        # State-restoration indicator (was position loaded from SQLite on this boot?)
        state_restored = bool(
            self._trader is not None and getattr(self._trader, "state_loaded", False)
        )
        state_db_path = str(getattr(self.settings, "state_db_path", ""))

        return {
            "mode": self.mode,
            "uptime_sec": uptime_sec,
            "uptime_seconds": uptime_sec,
            "msg_per_sec": msg_per_sec,
            "msg_rate": msg_per_sec,
            "latency_ms": self._latest_latency_ms,
            "latency_precision": "ms",
            "latest_price": str(self._latest_price) if self._latest_price is not None else None,
            "emergency_stopped": self.emergency_stopped,
            "kill_switch": self.emergency_stopped,
            # Money: numeric fields are quantized to satang (0.01 THB) so the
            # JSON-float display is clean and deterministic — no sub-satang
            # float noise (the old S3). The *_str twins carry the FULL-precision
            # Decimal verbatim and are the authoritative reconcile channel
            # (screen *_str == ledger, exact). Dashboard JS reads the numeric
            # fields; auditors/tests read *_str.
            "equity": float(quantize_price(equity)),
            "equity_str": str(equity),
            "cash": float(quantize_price(cash)),
            "cash_str": str(cash),
            "initial_capital": str(self._initial_capital),
            "pnl_today": float(quantize_price(pnl_today_dec)),
            "pnl_today_str": str(pnl_today_dec),
            "realized_today": float(quantize_price(realized_today)),
            "realized_today_str": str(realized_today),
            "daily_loss_pct": daily_loss_pct,
            "drawdown_pct": drawdown_pct,
            "positions": positions,
            "win_rate": win_rate,
            "backtest_win_rate": self._win_rate(),
            "wins": wins,
            "losses": losses,
            "trades_closed": trades_closed,
            "treasury_halted": halted,
            # Production-migration honesty: live PRICE feed. The execution
            # engine reflects the REAL configured mode (paper unless the
            # operator armed live behind all four gates) — never hardcoded,
            # so the dashboard cannot claim paper while orders fire live.
            "data_source": "live_bitkub_ws",
            "execution_engine": str(getattr(self.settings, "execution_engine", "paper")),
            # Price-feed health so the dashboard can explain a missing price
            # instead of showing a bare "—".
            "price_feed": {
                "mode": str(getattr(self.settings, "price_feed_mode", "rest")),
                "connected": self._latest_price is not None,
                "last_error": (
                    getattr(self.feed, "last_error", None) if self.feed is not None else None
                ),
            },
            # Phase A: real Bitkub account connected READ-ONLY when a key is set.
            "bitkub_account_connected": account_connected,
            "bitkub_reconciled": reconciled,
            "bitkub_balances": real_balances,
            "account": self.account_status(),
            "portfolio": portfolio,
            "wallet_value_thb": wallet_thb,
            "p50_latency_ms": p50_ms,
            "p95_latency_ms": p95_ms,
            "state_restored": state_restored,
            "state_db_path": state_db_path,
            "execution_warning": self._execution_warning(account_connected),
            "dropped_messages": self._count_dropped_messages(),
            "risk_settings": self.get_risk_settings(),
            "breaker": {
                "is_open": bool(self._circuit_breaker and self._circuit_breaker.is_open),
                "consecutive_losses": (
                    self._circuit_breaker.consecutive_losses
                    if self._circuit_breaker is not None else 0
                ),
                "max_consecutive_losses": (
                    self._circuit_breaker.max_consecutive_losses
                    if self._circuit_breaker is not None else 0
                ),
            },
            "execution_mode": self.get_execution_mode(),
            "live_orders_armed": self._live_orders_armed(),
            "timeline": self._timeline_status(),
            "entry_gate": self._entry_gate_status(),
            "daily": self._daily_status(),
            "news": dict(self.last_news),
            "agents": [self._agent_status(n, a) for n, a in self.agents.items()],
        }

    def _live_orders_armed(self) -> bool:
        """True only when real orders can actually fire RIGHT NOW: live mode +
        all four gates open + a signed gateway wired into the execution gate."""
        engine = str(getattr(self.settings, "execution_engine", "paper"))
        if engine != "live" or not all(self._live_gate_checklist().values()):
            return False
        # M2: a connected account must be RECONCILED (verified by a real wallet
        # read) before live orders fire. If the verify failed, degrade to paper
        # rather than trade against an unverified/zero-balance account.
        recon = self._reconciliation
        if recon is not None and not bool(getattr(recon, "is_reconciled", False)):
            return False
        gate = self.agents.get("risk_gate")
        gw = getattr(gate, "_rest_gateway", None) if gate is not None else None
        return bool(gw is not None and hasattr(gw, "place_bid"))

    def _execution_warning(self, account_connected: bool) -> str:
        """Truthful one-line execution banner for the dashboard."""
        if self._live_orders_armed():
            return (
                "🔴 LIVE: real orders WILL fire on Bitkub — all four safety "
                "gates are open and a signed account is connected."
            )
        prefix = (
            "Real Bitkub account connected READ-ONLY (live wallet). "
            if account_connected
            else "No Bitkub API key configured — paper over live prices. "
        )
        return prefix + (
            "Order firing is SIMULATED; live orders require arming all four "
            "safety gates (execution_engine=live + confirm token + no "
            "KILL_SWITCH + breaker closed) with an account connected."
        )

    def _timeline_status(self) -> dict[str, object]:
        """Timeline Analyst snapshot for the dashboard (win-prob + regime)."""
        tl = self._timeline
        if tl is None:
            return {"available": False}
        return {
            "available": True,
            "p_win": str(getattr(tl, "p_win", "0")),
            "p_win_pct": round(float(getattr(tl, "p_win", 0)) * 100, 1),
            "p_win_samples": int(getattr(tl, "p_win_samples", 0)),
            "regime": str(getattr(tl, "regime", "RANGE")),
            "past_win_rate": getattr(tl, "past_win_rate", None),
            "recent_win_rate": getattr(tl, "recent_win_rate", None),
            "min_p_win": str(self._dec_setting("min_p_win", "0.55")),
            "passes_gate": (
                int(getattr(tl, "p_win_samples", 0)) >= int(getattr(self.settings, "gate_min_samples", 8))
                and Decimal(str(getattr(tl, "p_win", "0"))) >= self._dec_setting("min_p_win", "0.55")
            ),
            "analysis": dict(getattr(tl, "analysis", {})),
        }

    def _entry_gate_status(self) -> dict[str, object]:
        tl = self._timeline
        samples = int(getattr(tl, "p_win_samples", 0)) if tl is not None else 0
        min_samples = int(getattr(self.settings, "gate_min_samples", 8))
        return {
            "enabled": self._entry_gate_enabled,
            "min_p_win": str(self._dec_setting("min_p_win", "0.55")),
            # Warmup progress: the gate refuses entries until the Timeline Analyst
            # has graded this many comparable historical setups.
            "samples": samples,
            "min_samples": min_samples,
            "warming_up": samples < min_samples,
            "blocked_by_reason": dict(self._gate_block_reasons),
            "blocked_total": sum(self._gate_block_reasons.values()),
        }

    def write_daily_summary(self) -> dict[str, object]:
        """Phase 5: upsert today's row in data/daily_summary.csv — every field
        derived from the real treasury ledger (net of fees)."""
        from pathlib import Path  # noqa: PLC0415

        from infrastructure.logging.daily_summary import (  # noqa: PLC0415
            build_summary_row,
            upsert_daily_summary,
        )

        tr = self._treasury
        if tr is None:
            return {}
        open_value = self._trader.open_market_value() if self._trader is not None else Decimal("0")
        row = build_summary_row(
            date=tr.day_key,
            start_equity=self._initial_capital,
            end_equity=tr.cash + open_value,
            pnl_net=tr.realized_today,
            fees_total=tr.fees_today,
            wins=tr.wins,
            losses=tr.losses,
            target_pct=self._target_daily_profit_pct,
        )
        upsert_daily_summary(Path("data/daily_summary.csv"), row)
        return row

    def _daily_status(self) -> dict[str, object]:
        """Daily trade-budget + profit-target progress (honest: a target, not a
        promise — the market decides whether it is reached)."""
        profit_pct = float(self.daily_profit_pct())
        target = float(self._target_daily_profit_pct)
        return {
            "trades_today": self.trades_today(),
            "max_trades_per_day": self._max_trades_per_day,
            "target_profit_pct": target,
            "profit_pct_today": round(profit_pct, 3),
            "target_reached": profit_pct >= target if target > 0 else False,
            "stop_at_target": self._stop_at_daily_target,
            "note": "เป้าหมาย ไม่ใช่การการันตี — ตลาดเป็นผู้กำหนด",
        }

    def _compute_wallet_value_thb(self, balances: dict[str, str]) -> dict[str, object]:
        """Compute wallet value in THB from real balances + real latest price."""
        if not balances:
            return {"total_thb": None, "entries": [], "price_unavailable": True}
        mark = self._latest_price
        entries: list[dict[str, object]] = []
        total_thb: Decimal | None = Decimal("0") if mark is not None else None
        for sym, amt_str in balances.items():
            try:
                amt = Decimal(amt_str)
            except Exception:
                continue
            if sym == "THB":
                value_thb: Decimal | None = amt
                unavailable = False
            elif mark is not None and sym in ("BTC", "THB_BTC"):
                value_thb = amt * mark
                unavailable = False
            else:
                value_thb = None
                unavailable = True
            entries.append({
                "symbol": sym,
                "qty": amt_str,
                "value_thb": str(value_thb) if value_thb is not None else None,
                "price_unavailable": unavailable,
            })
            if total_thb is not None and value_thb is not None:
                total_thb += value_thb
        return {
            "total_thb": str(total_thb) if total_thb is not None else None,
            "entries": entries,
            "price_unavailable": any(e["price_unavailable"] for e in entries),
        }

    def _count_dropped_messages(self) -> int:
        """Return total dropped messages across all bus implementations."""
        total = 0
        for bus in (self._bus_impl,):
            if bus is not None:
                total += getattr(bus, "dropped_messages", 0)
        return total
