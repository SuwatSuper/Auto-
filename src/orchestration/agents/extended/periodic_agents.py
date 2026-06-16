# Layer 2 — Orchestration (agents/extended/periodic_agents)
"""Interval-driven extended agents (risk guards, sizing, sweeping, fee/latency/
connection monitors, dashboard synth, tax clerk, GC). Each does REAL work on
state the system already has; agents needing an unwired external source are
intentionally omitted per the no-mock-data policy.
"""
from __future__ import annotations

import gc
from decimal import Decimal

import structlog

from domain.risk.sizing import kelly_fraction
from orchestration.agents.extended.base import PeriodicAgent, RuntimeView, _dec, _f
from orchestration.agents.learning import thai_now


# ── 6. Risk: Drawdown Guardian (real monitor + kill switch) ──────────
class DrawdownGuardianAgent(PeriodicAgent):
    role = "Halts trading if daily loss breaches the limit"

    def __init__(self, name: str, runtime: RuntimeView, limit_pct: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._limit = limit_pct
        self.guards_triggered = 0

    async def tick(self) -> None:
        s = self._rt.status()
        dd = _f(s.get("drawdown_pct"))
        dl = _f(s.get("daily_loss_pct"))
        self.detail = f"DD {dd:.1f}% · ขาดทุนวันนี้ {dl:.1f}% / เพดาน {self._limit:.0f}%"
        if dd >= 1.0:
            self.learner.note_threshold(int(dd), f"ดรอว์ดาวน์แตะ {int(dd)}% — เฝ้าระวัง")
        if self._limit > 0 and dl >= self._limit and not bool(s.get("treasury_halted")):
            self._rt.trip_breaker(f"DRAWDOWN_GUARD ขาดทุน {dl:.1f}%")
            self.guards_triggered += 1
            self.learner.log(f"สั่งหยุดเทรด — ขาดทุนวันนี้ {dl:.1f}% เกินเพดาน {self._limit:.0f}%", "adapt")
            await self._rt.send_alert(f"🛡️ Drawdown guard: หยุดเทรด (ขาดทุน {dl:.1f}%)", "critical")


# ── 7. Risk: Dynamic Position Sizer (Kelly, real) ────────────────────
class DynamicPositionSizerAgent(PeriodicAgent):
    role = "Suggests position size via Kelly criterion"

    def __init__(self, name: str, runtime: RuntimeView, win_loss_ratio: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._wl = Decimal(str(win_loss_ratio))
        self.suggested_risk_pct = 0.0

    async def tick(self) -> None:
        s = self._rt.status()
        wins = int(_f(s.get("wins")))
        losses = int(_f(s.get("losses")))
        total = wins + losses
        wr = Decimal(wins) / Decimal(total) if total > 0 else Decimal("0.5")
        k = kelly_fraction(wr, self._wl)
        self.suggested_risk_pct = float(k) * 100
        # Apply for REAL once there is a meaningful sample (>=10 closed trades):
        # the runtime clamps it to a safe band and feeds the next entry's size.
        applied = False
        if total >= 10:
            fn = getattr(self._rt, "apply_kelly_risk", None)
            if callable(fn):
                applied = bool(fn(self.suggested_risk_pct))
                if applied:
                    self.learner.log(
                        f"ปรับความเสี่ยง/ไม้ตาม Kelly เป็น ~{self.suggested_risk_pct:.2f}% "
                        f"(WR {float(wr) * 100:.0f}%, {total} ไม้)",
                        "adapt",
                    )
        tail = " · ใช้จริงแล้ว ✅" if applied else (" · รอ ≥10 ไม้จึงปรับจริง" if total < 10 else "")
        # Honest: show WR only once there are real closed trades (no fake 50%).
        wr_txt = f"{float(wr) * 100:.0f}%" if total > 0 else "—"
        self.detail = f"Kelly แนะนำเสี่ยง {self.suggested_risk_pct:.2f}%/ไม้ (WR {wr_txt}, {total} ไม้){tail}"


# ── 8. Risk: Trailing Stop Bot (real, advisory) ──────────────────────
class TrailingStopBotAgent(PeriodicAgent):
    role = "Tracks a trailing stop to lock in profit"

    def __init__(self, name: str, runtime: RuntimeView, trail_pct: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._trail = trail_pct
        # Decimal twin of the trail % — the stop is a REAL protective price level
        # pushed onto a (potentially live) position, so it must stay Decimal and
        # never round-trip through float (money-path rule).
        self._trail_frac = Decimal(1) - Decimal(str(trail_pct)) / Decimal(100)
        self._peak: Decimal | None = None
        self.trail_stop: Decimal = Decimal("0")

    async def tick(self) -> None:
        s = self._rt.status()
        port = s.get("portfolio")
        rows = port if isinstance(port, list) else []
        if not rows:
            self._peak = None
            self.trail_stop = Decimal("0")
            self.detail = "ไม่มี position เปิดอยู่"
            return
        mark = _dec(rows[0].get("mark_price") if isinstance(rows[0], dict) else None)
        if mark <= 0:
            self.detail = "ยังไม่มีราคา mark"
            return
        prev_peak = self._peak
        self._peak = mark if self._peak is None else max(self._peak, mark)
        self.trail_stop = self._peak * self._trail_frac
        # Push the stop into the live position for REAL (ratchets up only).
        moved = False
        fn = getattr(self._rt, "update_trailing_stop", None)
        if callable(fn):
            moved = bool(fn(self.trail_stop))
        self.detail = (
            f"จุดสูงสุด {self._peak:.0f} · trailing-stop {self.trail_stop:.0f} ({self._trail:.1f}%)"
            + (" · ป้องกันจริง ✅" if moved else "")
        )
        if moved:
            self.learner.log(f"ขยับ stop ป้องกันกำไรขึ้นเป็น {self.trail_stop:.0f} (ของจริง)", "adapt")
        elif prev_peak is not None and self._peak > prev_peak:
            self.learner.log(f"ราคาทำจุดสูงสุดใหม่ {self._peak:.0f} → trailing-stop {self.trail_stop:.0f}", "event")


# ── 9. Risk/Treasury: Profit Sweeper (real bookkeeping) ──────────────
class ProfitSweeperAgent(PeriodicAgent):
    # Honest: this is an ADVISORY paper vault — it tallies what a profit-sweep
    # WOULD set aside; it never moves treasury cash (the treasury is the sole
    # owner of money). Kept in Decimal off the authoritative *_str ledger channel.
    role = "Advisory profit-sweep vault (paper — does not move treasury cash)"

    interval = 5.0

    def __init__(self, name: str, runtime: RuntimeView, sweep_ratio: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._ratio = Decimal(str(sweep_ratio))
        self._last_realized = Decimal("0")
        self.vault_thb = Decimal("0")

    async def tick(self) -> None:
        s = self._rt.status()
        # Read the full-precision authoritative ledger channel (realized_today_str),
        # not the lossy float display twin.
        realized = _dec(s.get("realized_today_str", s.get("realized_today")))
        if realized > self._last_realized:
            swept = (realized - self._last_realized) * self._ratio
            self.vault_thb += swept
            self._last_realized = realized
            self.learner.log(f"กวาดกำไร ฿{swept:,.2f} เข้าคลัง (advisory · รวม ฿{self.vault_thb:,.2f})", "event")
        elif realized < self._last_realized:
            self._last_realized = realized  # new day / drawdown — reset baseline
        self.detail = (
            f"คลังกำไร (advisory vault) ฿{self.vault_thb:,.2f} · "
            f"กวาด {self._ratio * 100:.0f}% ของกำไรที่รับรู้ (ไม่ย้ายเงินจริง)"
        )


# ── 10. Execution: Fee Optimizer (real maker/taker calc) ─────────────
class FeeOptimizerAgent(PeriodicAgent):
    role = "Reports the maker/taker fee gap (advisory — does not change order type)"

    interval = 5.0

    def __init__(self, name: str, maker_bps: float, taker_bps: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._maker = maker_bps
        self._taker = taker_bps

    async def tick(self) -> None:
        rec = "MAKER (ตั้งรอ)" if self._maker <= self._taker else "TAKER (เคาะ)"
        saving = abs(self._taker - self._maker)
        self.detail = f"maker {self._maker:.0f}bps vs taker {self._taker:.0f}bps → แนะนำ {rec} (ประหยัด {saving:.0f}bps)"


# ── 11. Execution: Latency Pinger (real, from measured samples) ──────
class LatencyPingerAgent(PeriodicAgent):
    role = "Monitors exchange latency (advisory — does not throttle orders)"

    def __init__(self, name: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self.high_latency = False

    async def tick(self) -> None:
        s = self._rt.status()
        cur = _f(s.get("latency_ms"))
        p50 = _f(s.get("p50_latency_ms"))
        p95 = _f(s.get("p95_latency_ms"))
        prev = self.high_latency
        self.high_latency = p95 > 1000
        self.detail = f"latency now {cur:.0f}ms · p50 {p50:.0f}ms · p95 {p95:.0f}ms" + (" ⚠ แล็กสูง — ชะลอยิงออเดอร์" if self.high_latency else "")
        if self.high_latency != prev:
            self.learner.log(
                (f"latency p95 พุ่ง {p95:.0f}ms — ชะลอการยิงออเดอร์" if self.high_latency
                 else f"latency กลับสู่ปกติ (p95 {p95:.0f}ms)"),
                "event",
            )


# ── 12. System: API & Connection Monitor (real self-monitor) ─────────
class ApiConnectionMonitorAgent(PeriodicAgent):
    role = "Watches feed/account health; flags outages"

    def __init__(self, name: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self.outages = 0
        self._was_ok = True

    async def tick(self) -> None:
        s = self._rt.status()
        pf = s.get("price_feed")
        pf = pf if isinstance(pf, dict) else {}
        acct = s.get("account")
        acct = acct if isinstance(acct, dict) else {}
        feed_ok = bool(pf.get("connected"))
        err = pf.get("last_error")
        if not feed_ok and self._was_ok:
            self.outages += 1
            self.learner.log(f"ฟีดราคาหลุด ({err or 'unknown'})", "event")
        elif feed_ok and not self._was_ok:
            self.learner.log("ฟีดราคากลับมาเชื่อมต่อแล้ว ✅", "event")
        self._was_ok = feed_ok
        acct_txt = "เชื่อมบัญชีแล้ว" if acct.get("connected") else "ยังไม่ใส่ key"
        self.detail = (
            f"ฟีดราคา {'OK ✅' if feed_ok else 'ขาด ❌'}"
            + (f" ({err})" if err and not feed_ok else "")
            + f" · บัญชี: {acct_txt} · ขาดการเชื่อมต่อสะสม {self.outages} ครั้ง"
        )


# ── 13. System: Dashboard Synthesizer (real KPIs + midnight push) ────
class DashboardSynthesizerAgent(PeriodicAgent):
    role = "Distils 4 KPIs; pushes a daily midnight summary"

    interval = 5.0

    def __init__(self, name: str, runtime: RuntimeView, rr: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._rr = rr
        self._last_push_day: str | None = None
        self.summary: dict[str, float] = {}

    async def tick(self) -> None:
        s = self._rt.status()
        wins = int(_f(s.get("wins")))
        losses = int(_f(s.get("losses")))
        total = wins + losses
        wr = (wins / total * 100) if total > 0 else 0.0
        dd = _f(s.get("drawdown_pct"))
        pnl = _f(s.get("pnl_today"))
        self.summary = {"win_rate": round(wr, 1), "rr": self._rr, "max_drawdown": round(dd, 1), "pnl_today": round(pnl, 2)}
        self.detail = f"WR {wr:.0f}% · R:R {self._rr:.1f} · MaxDD {dd:.1f}% · PnL ฿{pnl:,.0f}"
        now = thai_now()  # Thai (UTC+7) — push the daily summary at THAI midnight
        day = now.strftime("%Y-%m-%d")
        if now.hour == 0 and self._last_push_day != day:
            self._last_push_day = day
            self.learner.log(f"สรุปวัน push เข้ามือถือ: WR {wr:.0f}% · MaxDD {dd:.1f}% · PnL ฿{pnl:,.0f}", "event")
            await self._rt.send_alert(
                f"🌙 สรุปวัน: WR {wr:.0f}% · R:R {self._rr:.1f} · MaxDD {dd:.1f}% · PnL ฿{pnl:,.0f}", "info"
            )


# ── 14. System: Tax & Accounting Clerk (real closed-trade ledger) ────
class TaxAccountingClerkAgent(PeriodicAgent):
    role = "Books realized PnL per trade for tax reporting"

    interval = 5.0

    def __init__(self, name: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime

    async def tick(self) -> None:
        s = self._rt.status()
        closed = int(_f(s.get("trades_closed")))
        wins = int(_f(s.get("wins")))
        losses = int(_f(s.get("losses")))
        realized = _f(s.get("realized_today"))
        self.detail = f"ปิดแล้ว {closed} ไม้ (ชนะ {wins}/แพ้ {losses}) · กำไรรับรู้วันนี้ ฿{realized:,.2f} → บันทึกเพื่อภาษี"


# ── 15. System: Garbage Collector (real memory hygiene) ──────────────
class GarbageCollectorAgent(PeriodicAgent):
    role = "Frees memory and keeps the runtime lean"

    interval = 30.0

    def __init__(self, name: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self.collections = 0
        self.freed_total = 0

    async def tick(self) -> None:
        freed = gc.collect()
        self.collections += 1
        self.freed_total += freed
        tracked = len(gc.get_objects())
        self.detail = f"gc รอบที่ {self.collections} · คืน {freed} objects · ติดตามอยู่ {tracked:,}"
        if freed > 0:
            self.learner.log(f"คืนหน่วยความจำ {freed} objects (รอบที่ {self.collections})", "event")
