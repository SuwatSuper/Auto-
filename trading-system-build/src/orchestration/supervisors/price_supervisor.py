from __future__ import annotations

import orjson
import structlog

from domain.trading.market_data import normalize_bitkub_ticker
from orchestration.ports.event_publisher import EventPublisher
from orchestration.ports.price_feed import PriceFeed


class PriceSupervisor:
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
        await self._feed.run(self._handle_raw)

    async def _handle_raw(self, raw: dict[str, object]) -> None:
        price_update = normalize_bitkub_ticker(raw, logger=self._log)
        if price_update is None:
            return
        payload = orjson.dumps(price_update.model_dump(mode="json"))
        await self._bus.publish(
            self._topic,
            key=price_update.symbol.encode(),
            value=payload,
        )
        self._log.info(
            "price_published",
            symbol=price_update.symbol,
            price=str(price_update.price),
            event_id=price_update.event_id,
        )
