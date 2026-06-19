from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol


class PriceFeed(Protocol):
    async def run(self, on_raw: Callable[[dict[str, object]], Awaitable[None]]) -> None: ...
