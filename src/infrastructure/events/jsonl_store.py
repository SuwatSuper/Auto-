# Layer 3 — Infrastructure (events/jsonl_store)
from __future__ import annotations

import asyncio
import os
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
        # H7: flush + fsync each append so a crash / power loss can't drop the
        # tail of the audit/replay log. The append is a single record terminated
        # by '\n', so a torn write leaves at most one partial trailing line,
        # which the reader skips (see read()).
        with path.open("ab") as f:
            f.write(payload + b"\n")
            f.flush()
            os.fsync(f.fileno())

    async def read(self, stream: str, from_seq: int = 0) -> AsyncIterator[tuple[int, bytes]]:
        path = self._stream_path(stream)
        if not path.exists():
            return
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, path.read_bytes)
        # H7: a crash mid-append can leave a partial last line with no trailing
        # newline. Only treat lines that were fully committed (newline-terminated)
        # as records, so a torn tail is never yielded as a valid (but truncated)
        # JSON event.
        complete = raw[: raw.rfind(b"\n") + 1] if b"\n" in raw else b""
        for seq, line in enumerate(complete.splitlines()):
            if seq >= from_seq and line.strip():
                yield seq, line
