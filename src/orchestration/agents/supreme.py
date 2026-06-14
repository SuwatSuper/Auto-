# Layer 2 — Orchestration (agents/supreme)
from __future__ import annotations

import asyncio
import time
from decimal import InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus


class SupremeAgent:
    """Final arbiter: turns department signals into decisions via a REAL
    rolling multi-agent consensus (not a 1:1 pass-through).

    Each signal carries a ``source`` (the agent that produced it). Supreme keeps
    the latest vote per source inside a sliding ``window_s`` and tallies
    net = (#sources BUY) − (#sources SELL). A decision EXECUTEs only when the
    net agreement meets ``buy_votes`` / ``sell_votes``; otherwise OBSERVE.

    Defaults (buy_votes=sell_votes=1) preserve the original behaviour — a single
    signal still executes — while letting the operator demand 2+ agreeing
    strategies for a stricter, less noisy entry.
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
        self.detail = ""

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
                    decision, consensus_signal, net = self._consensus(signal, source, now_ms)
                    self.decision_count += 1
                    decision_id = f"sup-{self.decision_count}-{int(time.time() * 1000)}"
                    out = orjson.dumps(
                        {
                            "decision": decision,
                            "signal": consensus_signal,
                            "decision_id": decision_id,
                            "net_votes": net,
                        }
                    )
                    await self._bus.publish(self._topic_out, b"supreme", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("supreme_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("supreme_agent.stopped")

    def _consensus(self, signal: str, source: str, now_ms: int) -> tuple[str, str, int]:
        """Record this vote, expire stale ones, and return (decision, signal, net)."""
        if signal in ("BUY", "SELL"):
            self._votes[source] = (signal, now_ms)
        # Expire votes older than the window.
        if self._window_ms > 0:
            self._votes = {
                s: (v, t) for s, (v, t) in self._votes.items()
                if now_ms - t <= self._window_ms
            }
        buys = sum(1 for v, _ in self._votes.values() if v == "BUY")
        sells = sum(1 for v, _ in self._votes.values() if v == "SELL")
        net = buys - sells
        # Long-only: a BUY opens, a SELL only closes. So a BUY entry fires on a
        # bullish MAJORITY meeting the vote floor (it is NOT cancelled vote-for-
        # vote by sells, which previously stalled entries in mixed markets); a
        # SELL (close) fires only when bears clearly outnumber bulls.
        if buys >= self._buy_votes and buys >= sells:
            decision, consensus = "EXECUTE", "BUY"
        elif sells >= self._sell_votes and sells > buys:
            decision, consensus = "EXECUTE", "SELL"
        else:
            decision, consensus = "OBSERVE", signal if signal in ("BUY", "SELL") else "HOLD"
        self.detail = (
            f"โหวต BUY {buys} / SELL {sells} (net {net:+d}) → {decision} {consensus} "
            f"· เกณฑ์ BUY≥{self._buy_votes}/SELL≥{self._sell_votes}"
        )
        return decision, consensus, net

    async def stop(self) -> None:
        self.running = False
