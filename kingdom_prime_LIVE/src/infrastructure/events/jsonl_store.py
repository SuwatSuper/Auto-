# Layer 3 — Infrastructure (events/jsonl_store)
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path


class JsonlEventStore:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._lock = asyncio.Lock()
        base_dir.mkdir(parents=True, exist_ok=True)

    def _stream_path(self, stream: str) -> Path:
        safe_name = stream.replace("/", "_").replace(":", "_")
        return self._base_dir / f"{safe_name}.jsonl"

    async def append(self, stream: str, payload: bytes) -> None:
        async with self._lock:
            path = self._stream_path(stream)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_append, path, payload)

    def _sync_append(self, path: Path, payload: bytes) -> None:
        with path.open("ab") as f:
            f.write(payload + b"\n")

    async def read(self, stream: str, from_seq: int = 0) -> AsyncIterator[tuple[int, bytes]]:
        path = self._stream_path(stream)
        if not path.exists():
            return
        loop = asyncio.get_event_loop()
        lines = await loop.run_in_executor(None, path.read_bytes)
        for seq, line in enumerate(lines.splitlines()):
            if seq >= from_seq and line.strip():
                yield seq, line
