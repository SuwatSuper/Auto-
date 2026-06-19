# Layer 3 — Infrastructure (state/sqlite_store)
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path


class SqliteStateStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            # check_same_thread=False: run_in_executor may use a different pool
            # thread per call. All access is serialized by self._lock, so the
            # connection is never used concurrently — only across threads.
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            # M6: this store holds money-critical state (positions, balances, the
            # circuit-breaker snapshot). FULL fsyncs the WAL on every commit so a
            # committed write survives a power loss — worth the small latency for
            # a low-write-rate control store.
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
            )
            self._conn.commit()
        return self._conn

    async def get(self, key: str) -> bytes | None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_get, key)

    def _sync_get(self, key: str) -> bytes | None:
        row = self._get_conn().execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return bytes(row[0]) if row else None

    async def set(self, key: str, value: bytes) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_set, key, value)

    def _sync_set(self, key: str, value: bytes) -> None:
        conn = self._get_conn()
        conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

    async def delete(self, key: str) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_delete, key)

    def _sync_delete(self, key: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM state WHERE key = ?", (key,))
        conn.commit()

    async def keys(self, prefix: str = "") -> list[str]:
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_keys, prefix)

    @staticmethod
    def _like_escape(s: str) -> str:
        """Escape LIKE metacharacters so a prefix containing '_' or '%' (both
        common in our dotted key names' neighbours) matches literally (M6)."""
        return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _sync_keys(self, prefix: str) -> list[str]:
        pattern = self._like_escape(prefix) + "%"
        cur = self._get_conn().execute(
            "SELECT key FROM state WHERE key LIKE ? ESCAPE '\\' ORDER BY key", (pattern,)
        )
        return [str(row[0]) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
