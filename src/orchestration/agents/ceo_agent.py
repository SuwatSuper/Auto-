# Layer 2 — Orchestration (agents/ceo_agent)
"""CeoAgent — Executive observer.

Subscribes to every decision/risk/paper topic, appends an immutable
DecisionRecord per relevant event, and exposes:

  * audit_view()       → AuditView (replayable answer to "ใครตัดสินใจ? เกิดอะไรขึ้น?")
  * snapshot_builder() → SystemSnapshot factory used to render ExecutiveSummary

This agent NEVER takes a trading action; it only OBSERVES. That is a
deliberate Layer-2 invariant — the CEO is a witness, not an executor.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Protocol

import orjson
import structlog

from domain.audit.decision_log import (
    AuditFilter,
    AuditView,
    DecisionOutcome,
    DecisionRecord,
    canonicalize,
    replay,
)
from domain.reporting.ceo_report import (
    AgentSnapshot,
    ExecutiveSummary,
    PositionSnapshot,
    SystemSnapshot,
    build_executive_summary,
)
from orchestration.ports.event_bus import EventBus

# Topics the CEO listens to. These are owned by Layer 2, not infrastructure.
_DEFAULT_TOPICS: tuple[str, ...] = (
    "signals.v1",
    "decisions.v1",
    "risk.v1",
    "paper.events.v1",
    "treasury.v1",
)


class _RuntimeView(Protocol):
    """The minimum surface the CEO needs from PipelineRuntime."""

    emergency_stopped: bool

    # Read-only property → covariant in the value type, so a concrete
    # ``dict[str, AgentLike]`` attribute satisfies this protocol member.
    @property
    def agents(self) -> Mapping[str, object]: ...

    def status(self) -> dict[str, object]: ...


class CeoAgent:
    """Observer agent. Aggregates decisions, never proposes them."""

    def __init__(
        self,
        bus: EventBus,
        logger: structlog.BoundLogger,
        runtime: _RuntimeView,
        agent_roles: dict[str, str],
        topics: Iterable[str] = _DEFAULT_TOPICS,
        max_records: int = 5_000,
    ) -> None:
        self._bus = bus
        self._log = logger.bind(agent="ceo")
        self._runtime = runtime
        self._agent_roles = dict(agent_roles)
        self._topics = tuple(topics)
        self._records: deque[DecisionRecord] = deque(maxlen=max_records)
        self._seq: int = 0
        self._feed_last_msg_ms: int | None = None
        self._latest_price: Decimal | None = None

        # AgentLike contract
        self.running: bool = False
        self.msg_count: int = 0
        self.last_beat_ms: int = 0
        self.parse_failures: int = 0
        self.decisions_recorded: int = 0

    # ── AgentLike lifecycle ──────────────────────────────────────

    async def start(self) -> None:
        self.running = True
        queues = {t: self._bus.subscribe(t) for t in self._topics}
        self._log.info("ceo_agent.started", topics=list(self._topics))
        pending: dict[str, asyncio.Task[bytes]] = {}
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                for topic, q in queues.items():
                    if topic not in pending or pending[topic].done():
                        pending[topic] = asyncio.create_task(q.get())
                done, _ = await asyncio.wait(
                    set(pending.values()),
                    timeout=0.5,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for topic, task in list(pending.items()):
                    if task in done:
                        try:
                            raw = task.result()
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            self._log.warning("ceo_agent.consume_error", topic=topic,
                                              exc_info=True)
                            pending.pop(topic, None)
                            continue
                        await self._ingest(topic, raw)
                        pending.pop(topic, None)
        finally:
            for task in pending.values():
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            for topic, q in queues.items():
                self._bus.unsubscribe(topic, q)
            self._log.info("ceo_agent.stopped",
                           decisions_recorded=self.decisions_recorded)

    async def stop(self) -> None:
        self.running = False

    # ── ingestion ────────────────────────────────────────────────

    async def _ingest(self, topic: str, raw: bytes) -> None:
        self.msg_count += 1
        try:
            data: dict[str, object] = orjson.loads(raw)
        except orjson.JSONDecodeError:
            self.parse_failures += 1
            self._log.warning("ceo_agent.parse_error", topic=topic, exc_info=True)
            return

        record = self._record_for(topic, data)
        if record is None:
            return
        self._seq += 1
        self._records.append(record)
        self.decisions_recorded += 1
        # Bound logging: log only at INFO with the minimal fields (the full record is in the ledger)
        self._log.info(
            "ceo_agent.decision_recorded",
            seq=record.seq, agent=record.agent, action=record.action,
            outcome=record.outcome.value, confidence=str(record.confidence),
        )

    def _record_for(self, topic: str, data: dict[str, object]) -> DecisionRecord | None:
        """Map a raw bus event onto an immutable DecisionRecord.

        Returns None for events we deliberately skip (e.g. price ticks).
        Defensive parsing: missing/invalid fields → SKIPPED outcome with reason.
        """
        ts_ms_val = data.get("ts_ms")
        ts_ms: int = int(ts_ms_val) if isinstance(ts_ms_val, int) else int(time.time() * 1000)

        if topic == "decisions.v1":
            return self._record_decision(data, ts_ms, topic)
        if topic == "signals.v1":
            return self._record_signal(data, ts_ms, topic)
        if topic == "risk.v1":
            return self._record_risk(data, ts_ms, topic)
        if topic == "paper.events.v1":
            return self._record_paper(data, ts_ms, topic)
        if topic == "treasury.v1":
            return self._record_treasury(data, ts_ms, topic)
        return None

    def _record_decision(
        self, data: dict[str, object], ts_ms: int, topic: str,
    ) -> DecisionRecord:
        decision = str(data.get("decision", "UNKNOWN"))
        signal = str(data.get("signal", ""))
        confidence = _safe_confidence(data.get("confidence"))
        reason = str(data.get("reason", "no reason given"))[:500]
        outcome = (
            DecisionOutcome.EXECUTED if decision == "EXECUTE"
            else DecisionOutcome.REJECTED if decision == "REJECT"
            else DecisionOutcome.SKIPPED
        )
        return DecisionRecord(
            ts_ms=ts_ms, seq=self._seq + 1,
            agent="supreme_commander",
            topic=topic, action=signal or decision,
            outcome=outcome, confidence=confidence,
            reason=reason,
            inputs=canonicalize({k: v for k, v in data.items()
                                 if k not in {"decision", "signal", "ts_ms", "confidence"}}),
            result=canonicalize({"decision": decision}),
        )

    def _record_signal(
        self, data: dict[str, object], ts_ms: int, topic: str,
    ) -> DecisionRecord:
        signal = str(data.get("signal", "HOLD"))
        confidence = _safe_confidence(data.get("confidence"))
        return DecisionRecord(
            ts_ms=ts_ms, seq=self._seq + 1,
            agent=str(data.get("source", "market_analyst")),
            topic=topic, action=f"SIGNAL_{signal}",
            outcome=DecisionOutcome.APPROVED,
            confidence=confidence,
            reason=str(data.get("reason", ""))[:500],
            inputs=canonicalize({k: v for k, v in data.items()
                                 if k not in {"signal", "ts_ms", "confidence", "source"}}),
            result=canonicalize({"signal": signal}),
        )

    def _record_risk(
        self, data: dict[str, object], ts_ms: int, topic: str,
    ) -> DecisionRecord:
        # The RiskAgent publishes {"approved": bool, "reasons": [...]} on risk.v1.
        # Reading a non-existent "verdict" field defaulted EVERY decision to
        # PASS/APPROVED — the audit trail silently mislabelled every rejection as
        # an approval. Read the real field.
        approved = bool(data.get("approved", True))
        verdict = "PASS" if approved else "REJECT"
        outcome = DecisionOutcome.APPROVED if approved else DecisionOutcome.REJECTED
        return DecisionRecord(
            ts_ms=ts_ms, seq=self._seq + 1,
            agent="risk_management", topic=topic,
            action=f"RISK_{verdict}",
            outcome=outcome,
            confidence=_safe_confidence(data.get("confidence")),
            reason=str(data.get("reason", ""))[:500],
            inputs=canonicalize({k: v for k, v in data.items()
                                 if k not in {"approved", "ts_ms", "confidence"}}),
            result=canonicalize({"verdict": verdict, "approved": approved}),
        )

    def _record_paper(
        self, data: dict[str, object], ts_ms: int, topic: str,
    ) -> DecisionRecord:
        kind = str(data.get("type", "UNKNOWN"))
        outcome = (
            DecisionOutcome.EXECUTED if kind in {"FILL", "CLOSE"}
            else DecisionOutcome.REJECTED if kind == "ENTRY_REJECTED"
            else DecisionOutcome.FAILED if kind == "ERROR"
            else DecisionOutcome.SKIPPED
        )
        return DecisionRecord(
            ts_ms=ts_ms, seq=self._seq + 1,
            agent="paper_trader", topic=topic,
            action=f"PAPER_{kind}",
            outcome=outcome,
            confidence=Decimal("1.0"),
            reason=str(data.get("reason", kind))[:500],
            inputs=(),
            result=canonicalize({k: v for k, v in data.items()
                                 if k not in {"type", "ts_ms"}}),
        )

    def _record_treasury(
        self, data: dict[str, object], ts_ms: int, topic: str,
    ) -> DecisionRecord:
        kind = str(data.get("type", "STATUS"))
        outcome = (
            DecisionOutcome.FAILED if kind == "HALT"
            else DecisionOutcome.APPROVED
        )
        return DecisionRecord(
            ts_ms=ts_ms, seq=self._seq + 1,
            agent="treasury", topic=topic,
            action=f"TREASURY_{kind}",
            outcome=outcome,
            confidence=Decimal("1.0"),
            reason=str(data.get("reason", kind))[:500],
            inputs=(),
            result=canonicalize({k: v for k, v in data.items()
                                 if k not in {"type", "ts_ms"}}),
        )

    # ── public queries (for the API / dashboard) ─────────────────

    def audit_view(self, flt: AuditFilter | None = None) -> AuditView:
        return replay(list(self._records), flt)

    def executive_summary(self) -> ExecutiveSummary:
        """Build an ExecutiveSummary from the runtime's current state."""
        return build_executive_summary(self._build_snapshot())

    def _build_snapshot(self) -> SystemSnapshot:
        # Pull the live status dict (no I/O — Layer-2 in-memory).
        status = self._runtime.status()
        now_ms = int(time.time() * 1000)

        cash_str = status.get("cash")
        cash = _safe_decimal(cash_str)
        equity_str = status.get("equity_str") or status.get("equity")
        equity = _safe_decimal(equity_str)
        latest_price_raw = status.get("latest_price")
        latest_price = _safe_decimal(latest_price_raw)

        # Use the runtime's REAL running peak (via its measured drawdown_pct) so
        # the executive drawdown matches reality. The old max(equity, initial)
        # could never be below current equity, so it understated every drawdown
        # after a pullback from a profit peak. dd = (peak-equity)/peak  ⇒
        # peak = equity / (1 - dd/100) — exact reconstruction of the true peak.
        _initial_cap = _safe_decimal(status.get("initial_capital")) or Decimal("0")
        _dd_pct = _safe_decimal(status.get("drawdown_pct")) or Decimal("0")
        if equity is None:
            peak_equity = _initial_cap
        elif _dd_pct > 0:
            peak_equity = equity / (Decimal("1") - _dd_pct / Decimal("100"))
        else:
            peak_equity = equity  # drawdown 0 ⇒ currently at the peak

        pnl_today_raw = status.get("pnl_today")
        pnl_today = _safe_decimal(pnl_today_raw)

        # Positions: the runtime exposes an integer count but not the
        # individual positions, so we report empty unless richer info is wired.
        positions: tuple[PositionSnapshot, ...] = ()

        agent_snaps: list[AgentSnapshot] = []
        agents_raw = status.get("agents", [])
        agents_list = agents_raw if isinstance(agents_raw, list) else []
        for entry in agents_list:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", ""))
            beat = int(entry.get("last_beat_ms", 0) or 0)
            agent_snaps.append(AgentSnapshot(
                name=name,
                role=self._agent_roles.get(name, "—"),
                running=bool(entry.get("running", False)),
                last_beat_ms=beat,
                msg_count=int(entry.get("msg_count", 0) or 0),
                stale=bool(entry.get("stale", False)),
                crashed=bool(entry.get("crashed", False)),
                crash_reason=entry.get("crash_reason") if entry.get("crash_reason") else None,
                restarts=int(entry.get("restarts", 0) or 0),
            ))

        return SystemSnapshot(
            now_ms=now_ms,
            initial_capital=_safe_decimal(status.get("initial_capital")) or Decimal("0"),
            cash=cash,
            peak_equity=peak_equity,
            realized_pnl_today=pnl_today,
            positions=positions,
            latest_price=latest_price,
            feed_connected=latest_price is not None,
            feed_last_msg_ms=self._feed_last_msg_ms,
            agents=tuple(agent_snaps),
            treasury_halted=bool(status.get("treasury_halted", False)),
            emergency_stopped=bool(status.get("emergency_stopped", False)),
        )


def _safe_decimal(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _safe_confidence(v: object) -> Decimal:
    """Map any value into [0,1] Decimal. Defaults to 0.5 (no information)."""
    dec = _safe_decimal(v)
    if dec is None:
        return Decimal("0.5")
    if dec < Decimal("0"):
        return Decimal("0")
    if dec > Decimal("1"):
        return Decimal("1")
    return dec
