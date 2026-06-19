# Layer 2 — Orchestration (agents/learning)
"""Outcome-feedback self-improvement engine — REAL, no LLM, no fabricated data.

Every number an agent's Learner reports traces to a real event:
  • Execution    — the agent records each prediction it makes (signal + price + ts)
  • Reflection   — the prediction is later graded against the REAL price that
                   followed (win / loss), giving a measured hit-rate
  • Refinement   — the agent tightens/relaxes its own parameters from that
                   hit-rate and keeps a journal of every change + every mistake

A daily score (0–100) and a timestamped learning journal are produced so the
operator can verify, minute by minute, that the agent is genuinely working.

NOTE: This is a statistical/adaptive loop, not an LLM-in-the-loop. An optional
LLM critic can be layered on later (off until an API key is provided) — this
module never pretends an LLM is involved.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Thailand is the operating jurisdiction; the trading "day" is anchored to a
# FIXED UTC+7 offset so day-rollover is identical on any host clock (a cloud VPS
# or CI box is rarely set to Asia/Bangkok). This keeps the per-agent daily
# counters aligned with the treasury's authoritative Thai day-key instead of
# drifting with the machine's local zone.
_THAI_TZ = timezone(timedelta(minutes=420))


def thai_now() -> datetime:
    """Current time in Thailand (UTC+7), host-clock-independent."""
    return datetime.now(tz=_THAI_TZ)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _today() -> str:
    return thai_now().strftime("%Y-%m-%d")


def _as_int(value: object, default: int = 0) -> int:
    """Best-effort int coercion for restored memory (never raises)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _as_float(value: object, default: float) -> float:
    """Best-effort float coercion for restored memory (never raises)."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


@dataclass
class JournalEntry:
    ts_ms: int
    kind: str   # outcome | adapt | coach | event | day | info
    text: str

    def as_dict(self) -> dict[str, object]:
        return {"ts_ms": self.ts_ms, "kind": self.kind, "text": self.text}


@dataclass
class Learner:
    """Per-agent learning state. ``kind`` is 'strategy' (graded on real signal
    outcomes) or 'reliability' (graded on uptime/activity)."""

    name: str
    kind: str = "reliability"
    journal: deque[JournalEntry] = field(default_factory=lambda: deque(maxlen=150))
    # cumulative + daily real outcome counters
    resolved: int = 0
    correct: int = 0
    today_resolved: int = 0
    today_correct: int = 0
    adapt_count: int = 0
    score: float = 50.0
    _open: list[tuple[int, str, Decimal]] = field(default_factory=list)
    _day: str = field(default_factory=_today)
    _last_seen_pct: int = -1  # for de-duping threshold-crossing logs

    # ── journaling ────────────────────────────────────────────────
    def log(self, text: str, kind: str = "info") -> None:
        self.journal.append(JournalEntry(_now_ms(), kind, text))

    def recent(self, limit: int = 20) -> list[dict[str, object]]:
        items = list(self.journal)[-limit:]
        return [e.as_dict() for e in reversed(items)]

    def recent_mistakes(self, limit: int = 5) -> list[dict[str, object]]:
        """Recent graded LOSSES — the real mistakes this agent made."""
        out = [
            e.as_dict() for e in reversed(self.journal)
            if e.kind == "outcome" and "❌" in e.text
        ]
        return out[:limit]

    def recent_improvements(self, limit: int = 5) -> list[dict[str, object]]:
        """Recent parameter changes the agent made to improve (adapt/coach)."""
        out = [
            e.as_dict() for e in reversed(self.journal)
            if e.kind in ("adapt", "coach")
        ]
        return out[:limit]

    # ── execution → reflection (real outcome grading) ─────────────
    def predict(self, action: str, price: Decimal, ts_ms: int) -> None:
        self._open.append((ts_ms, action, price))
        if len(self._open) > 300:
            self._open = self._open[-300:]

    def resolve(
        self, price: Decimal, ts_ms: int, horizon_ms: int = 60_000, edge: Decimal = Decimal("0.001")
    ) -> None:
        """Grade matured predictions against the REAL price that followed."""
        still_open: list[tuple[int, str, Decimal]] = []
        for t, act, entry in self._open:
            if ts_ms - t < horizon_ms:
                still_open.append((t, act, entry))
                continue
            if entry <= 0:
                continue
            move = (price - entry) / entry
            if abs(move) < edge:
                continue  # ambiguous — discard (never counted, never faked)
            win = (act == "BUY" and move >= edge) or (act == "SELL" and move <= -edge)
            self.resolved += 1
            self.today_resolved += 1
            if win:
                self.correct += 1
                self.today_correct += 1
            self.log(
                f"ผล {act} @{entry:.0f} → {price:.0f}: "
                f"{'✅ ถูก' if win else '❌ ผิด'} ({move * 100:+.2f}%)",
                "outcome",
            )
        self._open = still_open

    def hit_rate(self) -> float | None:
        return self.correct / self.resolved if self.resolved else None

    def today_hit_rate(self) -> float | None:
        return self.today_correct / self.today_resolved if self.today_resolved else None

    def roll_day(self) -> None:
        d = _today()
        if d != self._day:
            self._day = d
            self.today_resolved = 0
            self.today_correct = 0
            # M5: reset the threshold de-dup so a new day's drawdown alerts can
            # fire again (they were otherwise suppressed for the process lifetime).
            self._last_seen_pct = -1
            self.log("เริ่มวันใหม่ — รีเซ็ตคะแนนรายวัน", "day")

    def note_threshold(self, pct: int, text: str) -> None:
        """Log a threshold crossing once (de-duped by integer percent bucket)."""
        if pct != self._last_seen_pct:
            self._last_seen_pct = pct
            self.log(text, "event")

    # ── persistence (memory that survives shutdown) ───────────────────
    def to_dict(self, journal_limit: int = 40) -> dict[str, object]:
        """Serialize this agent's memory — counters + the most recent journal
        entries (its real mistakes and the fixes it made) — for disk storage."""
        return {
            "name": self.name,
            "kind": self.kind,
            "resolved": self.resolved,
            "correct": self.correct,
            "today_resolved": self.today_resolved,
            "today_correct": self.today_correct,
            "adapt_count": self.adapt_count,
            "score": self.score,
            "day": self._day,
            "journal": [e.as_dict() for e in list(self.journal)[-journal_limit:]],
        }

    def load_dict(self, data: dict[str, object]) -> None:
        """Restore memory saved by :meth:`to_dict` (best-effort, never raises)."""
        self.resolved = _as_int(data.get("resolved"))
        self.correct = _as_int(data.get("correct"))
        self.today_resolved = _as_int(data.get("today_resolved"))
        self.today_correct = _as_int(data.get("today_correct"))
        self.adapt_count = _as_int(data.get("adapt_count"))
        self.score = _as_float(data.get("score"), 50.0)
        if isinstance(data.get("day"), str):
            self._day = str(data["day"])
        entries = data.get("journal", [])
        if isinstance(entries, list):
            restored: deque[JournalEntry] = deque(maxlen=150)
            for e in entries:
                if not isinstance(e, dict):
                    continue
                restored.append(
                    JournalEntry(_as_int(e.get("ts_ms")), str(e.get("kind", "info")), str(e.get("text", "")))
                )
            self.journal = restored


def reliability_score(
    *, running: bool, stale: bool, crashed: bool, restarts: int, msg_count: int
) -> float:
    """0–100 reliability from REAL lifecycle state."""
    if crashed:
        return 0.0
    if not running:
        return 0.0
    base = 100.0 if not stale else 45.0
    base -= min(30.0, restarts * 10.0)
    if msg_count == 0:
        base = min(base, 55.0)  # alive but still waiting for data
    return max(0.0, min(100.0, base))


def blended_score(reliability: float, learner: Learner) -> float:
    """Strategy agents are judged mostly on REAL accuracy; others on reliability."""
    if learner.kind == "strategy" and learner.resolved >= 5:
        hr = (learner.correct / learner.resolved) * 100.0
        return max(0.0, min(100.0, 0.35 * reliability + 0.65 * hr))
    return reliability
