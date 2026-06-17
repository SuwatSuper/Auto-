# Layer 2 — Orchestration (agents/supreme)
from __future__ import annotations

import asyncio
import time
from decimal import InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus

# Dynamic-weight bounds (Task 2). A muted source contributes 0 (its vote is
# ignored), a neutral one 1.0, a proven one up to MAX_WEIGHT. Driven by the
# source's MEASURED trade win-rate, routed back from paper.events by the runtime.
MUTED_WEIGHT = 0.0
NEUTRAL_WEIGHT = 1.0
MAX_WEIGHT = 2.0


class SupremeAgent:
    """Final arbiter: turns department signals into decisions via a REAL
    rolling, WEIGHTED multi-agent consensus (not a 1:1 pass-through).

    Each signal carries a ``source`` (the agent that produced it). Supreme keeps
    the latest vote per source inside a sliding ``window_s`` and tallies a
    *weighted* sum per side, where each source's weight reflects its measured
    trade win-rate (Task 2 — dynamic weighting):

      • win-rate > 55%  → weight > 1.0 (heard louder, up to MAX_WEIGHT)
      • win-rate < 45%  → weight 0.0 (muted: its vote is ignored)
      • otherwise / unproven → weight 1.0 (neutral)

    A decision EXECUTEs only when the weighted agreement meets ``buy_votes`` /
    ``sell_votes``; otherwise OBSERVE. Defaults (buy_votes=sell_votes=1, all
    weights 1.0) preserve the original behaviour — a single signal still
    executes — while letting proven strategies dominate and losers fall silent.
    """

    def __init__(
        self,
        bus: EventBus,
        topic_in: str,
        topic_out: str,
        logger: structlog.BoundLogger,
        window_s: float = 8.0,
        buy_votes: int = 1,
        sell_votes: int = 1,
    ) -> None:
        self._bus = bus
        self._topic_in = topic_in
        self._topic_out = topic_out
        self._log = logger
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self.decision_count = 0
        self._window_ms = int(max(0.0, window_s) * 1000)
        self._buy_votes = max(1, buy_votes)
        self._sell_votes = max(1, sell_votes)
        # source -> (vote: "BUY"|"SELL", ts_ms)
        self._votes: dict[str, tuple[str, int]] = {}
        # source -> dynamic vote weight (Task 2). Absent => NEUTRAL_WEIGHT.
        self._weights: dict[str, float] = {}
        self.detail = ""

    # ── dynamic weighting surface (Task 2) ───────────────────────────
    def set_source_weight(self, source: str, weight: float) -> None:
        """Set one source's vote weight (clamped to [MUTED, MAX]). Called by the
        runtime's paper.events feedback loop as real win-rates accrue."""
        self._weights[source] = max(MUTED_WEIGHT, min(MAX_WEIGHT, float(weight)))

    def update_weights(self, weights: dict[str, float]) -> None:
        """Bulk-update source weights (clamped). Pure setter — no hidden coupling:
        the runtime owns both ends and pushes weights in through this method."""
        for src, w in weights.items():
            self.set_source_weight(src, w)

    def weight_of(self, source: str) -> float:
        return self._weights.get(source, NEUTRAL_WEIGHT)

    def weights_snapshot(self) -> dict[str, float]:
        """Current non-neutral weights, for the dashboard / status surface."""
        return dict(self._weights)

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("supreme_agent.started")
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    async with asyncio.timeout(0.5):
                        raw = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data = orjson.loads(raw)
                    signal = str(data.get("signal", "HOLD"))
                    source = str(data.get("source", "default"))
                    now_ms = int(data.get("ts_ms", 0)) or int(time.time() * 1000)
                    decision, consensus_signal, net, voters = self._consensus(
                        signal, source, now_ms
                    )
                    self.decision_count += 1
                    decision_id = f"sup-{self.decision_count}-{int(time.time() * 1000)}"
                    out = orjson.dumps(
                        {
                            "decision": decision,
                            "signal": consensus_signal,
                            "decision_id": decision_id,
                            "net_votes": net,
                            # Provenance for Task-2 attribution: which sources made
                            # up the winning side. Routed through to paper.events so
                            # the trade outcome can credit/blame the right agents.
                            "voters": voters,
                        }
                    )
                    await self._bus.publish(self._topic_out, b"supreme", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("supreme_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("supreme_agent.stopped")

    def _consensus(
        self, signal: str, source: str, now_ms: int
    ) -> tuple[str, str, float, list[str]]:
        """Record this vote, expire stale ones, and return
        (decision, signal, weighted_net, winning_side_voters)."""
        if signal in ("BUY", "SELL"):
            self._votes[source] = (signal, now_ms)
        # Expire votes older than the window.
        if self._window_ms > 0:
            self._votes = {
                s: (v, t) for s, (v, t) in self._votes.items()
                if now_ms - t <= self._window_ms
            }
        # Weighted tallies (Task 2). A muted source (weight 0) contributes 0.
        buy_sources = [s for s, (v, _) in self._votes.items() if v == "BUY"]
        sell_sources = [s for s, (v, _) in self._votes.items() if v == "SELL"]
        buys = round(sum(self.weight_of(s) for s in buy_sources), 4)
        sells = round(sum(self.weight_of(s) for s in sell_sources), 4)
        net = round(buys - sells, 4)
        # Long-only: a BUY opens, a SELL only closes. A BUY entry fires on a
        # weighted bullish MAJORITY meeting the vote floor (not cancelled
        # vote-for-vote by sells); a SELL (close) fires only when bears clearly
        # outweigh bulls. Voters credited are the *winning* side's live sources.
        if buys >= self._buy_votes and buys >= sells:
            decision, consensus, voters = "EXECUTE", "BUY", buy_sources
        elif sells >= self._sell_votes and sells > buys:
            decision, consensus, voters = "EXECUTE", "SELL", sell_sources
        else:
            decision = "OBSERVE"
            consensus = signal if signal in ("BUY", "SELL") else "HOLD"
            voters = []
        self.detail = (
            f"โหวต(ถ่วงน้ำหนัก) BUY {buys:g} / SELL {sells:g} (net {net:+g}) → "
            f"{decision} {consensus} · เกณฑ์ BUY≥{self._buy_votes}/SELL≥{self._sell_votes}"
        )
        return decision, consensus, net, voters

    async def stop(self) -> None:
        self.running = False
