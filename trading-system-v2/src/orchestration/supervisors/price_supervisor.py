# Layer 2 — Orchestration (supervisors/price_supervisor)
"""PriceSupervisor: bridges the raw price feed into the typed event bus."""
from __future__ import annotations

import time

import orjson
import structlog

from domain.trading.market_data import NormalizationFailure, normalize_bitkub_ticker
from orchestration.ports.event_publisher import EventPublisher
from orchestration.ports.price_feed import PriceFeed


class PriceSupervisor:
    """Consumes raw feed messages, normalizes them, and publishes to the bus."""

    def __init__(
        self,
        feed: PriceFeed,
        bus: EventPublisher,
        topic: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self._feed = feed
        self._bus = bus
        self._topic = topic
        self._log = logger

    async def run(self) -> None:
        """Run forever, forwarding normalized price events."""
        await self._feed.run(self._handle_raw)

    async def _handle_raw(self, raw: dict[str, object]) -> None:
        now_ms = int(time.time() * 1000)
        result = normalize_bitkub_ticker(raw, now_ms=now_ms)
        if isinstance(result, NormalizationFailure):
            self._log.warning(
                "price_supervisor.normalization_failure", reason=result.reason
            )
            return
        payload = orjson.dumps(result.model_dump(mode="json"))
        await self._bus.publish(
            self._topic,
            key=result.symbol.encode(),
            value=payload,
        )
        self._log.info(
            "price_published",
            symbol=result.symbol,
            price=str(result.price),
            event_id=result.event_id,
        )
