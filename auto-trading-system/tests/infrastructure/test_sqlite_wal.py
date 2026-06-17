# tests/infrastructure/test_sqlite_wal.py
"""Item 8 (P1-5): SQLite WAL mode is enabled on connect."""
from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.state.sqlite_store import SqliteStateStore


@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path: Path) -> None:
    """SQLite store sets WAL journal mode on connect."""
    store = SqliteStateStore(tmp_path / "test.db")
    await store.set("ping", b"pong")

    conn = store._get_conn()
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row is not None
    assert row[0] == "wal"


@pytest.mark.asyncio
async def test_busy_timeout_set(tmp_path: Path) -> None:
    """SQLite store sets busy_timeout to 5000ms."""
    store = SqliteStateStore(tmp_path / "test.db")
    await store.set("ping", b"pong")

    conn = store._get_conn()
    row = conn.execute("PRAGMA busy_timeout").fetchone()
    assert row is not None
    assert int(row[0]) == 5000
