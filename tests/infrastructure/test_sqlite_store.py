# Layer 3 — Infrastructure (tests/infrastructure/test_sqlite_store)
"""SqliteStateStore contract tests, including the keys() listing."""
from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.state.sqlite_store import SqliteStateStore


@pytest.mark.asyncio
async def test_get_set_delete_roundtrip(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "s.db")
    assert await store.get("missing") is None
    await store.set("a", b"1")
    assert await store.get("a") == b"1"
    await store.set("a", b"2")  # upsert
    assert await store.get("a") == b"2"
    await store.delete("a")
    assert await store.get("a") is None
    store.close()


@pytest.mark.asyncio
async def test_keys_prefix_listing(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "k.db")
    await store.set("paper.position.v1", b"1")
    await store.set("treasury.account.v1", b"2")
    await store.set("paper.events.cursor", b"3")
    assert await store.keys("paper.") == ["paper.events.cursor", "paper.position.v1"]
    assert await store.keys() == [
        "paper.events.cursor",
        "paper.position.v1",
        "treasury.account.v1",
    ]
    store.close()


@pytest.mark.asyncio
async def test_values_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    s1 = SqliteStateStore(db)
    await s1.set("treasury.account.v1", b'{"cash":"987.65"}')
    s1.close()
    s2 = SqliteStateStore(db)
    assert await s2.get("treasury.account.v1") == b'{"cash":"987.65"}'
    s2.close()
