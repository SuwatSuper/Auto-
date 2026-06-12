# Layer 3 — Infrastructure (tests/infrastructure/test_stores)
"""Tests for SqliteStateStore, JsonlEventStore, InMemoryStateStore, InMemoryEventStore."""
from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.events.jsonl_store import JsonlEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from infrastructure.state.sqlite_store import SqliteStateStore


# --- InMemoryStateStore ---

async def test_inmemory_state_get_missing() -> None:
    store = InMemoryStateStore()
    assert await store.get("missing") is None


async def test_inmemory_state_set_get() -> None:
    store = InMemoryStateStore()
    await store.set("key1", b"value1")
    assert await store.get("key1") == b"value1"


async def test_inmemory_state_keys() -> None:
    store = InMemoryStateStore()
    await store.set("prefix.a", b"1")
    await store.set("prefix.b", b"2")
    await store.set("other", b"3")
    keys = await store.keys("prefix.")
    assert set(keys) == {"prefix.a", "prefix.b"}


async def test_inmemory_state_keys_all() -> None:
    store = InMemoryStateStore()
    await store.set("a", b"1")
    await store.set("b", b"2")
    keys = await store.keys()
    assert set(keys) == {"a", "b"}


# --- SqliteStateStore ---

async def test_sqlite_state_get_missing(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "test.db")
    assert await store.get("missing") is None


async def test_sqlite_state_set_get(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "test.db")
    await store.set("k", b"hello")
    assert await store.get("k") == b"hello"


async def test_sqlite_state_overwrite(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "test.db")
    await store.set("k", b"v1")
    await store.set("k", b"v2")
    assert await store.get("k") == b"v2"


async def test_sqlite_state_delete(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "test.db")
    await store.set("k", b"val")
    await store.delete("k")
    assert await store.get("k") is None


async def test_sqlite_state_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "persist.db"
    store1 = SqliteStateStore(db)
    await store1.set("key", b"persistent_value")

    store2 = SqliteStateStore(db)
    assert await store2.get("key") == b"persistent_value"


# --- InMemoryEventStore ---

async def test_inmemory_event_store_append_replay() -> None:
    import json
    store = InMemoryEventStore()
    env = json.dumps({"event_id": "e1", "ts_ms": 1000}).encode()
    await store.append(env)
    results = await store.replay(from_ms=0, to_ms=2000)
    assert len(results) == 1
    assert results[0] == env


async def test_inmemory_event_store_replay_filter() -> None:
    import json
    store = InMemoryEventStore()
    for ts in [1000, 2000, 3000, 4000]:
        env = json.dumps({"ts_ms": ts}).encode()
        await store.append(env)
    results = await store.replay(from_ms=2000, to_ms=3000)
    assert len(results) == 2


async def test_inmemory_event_store_empty_replay() -> None:
    store = InMemoryEventStore()
    results = await store.replay(from_ms=0, to_ms=9999)
    assert results == []


# --- JsonlEventStore ---

async def test_jsonl_store_append_read(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path)
    await store.append("stream1", b'{"e":"a"}')
    results = [(seq, data) async for seq, data in store.read("stream1")]
    assert len(results) == 1
    assert results[0][1] == b'{"e":"a"}'


async def test_jsonl_store_empty_stream(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path)
    results = [(seq, data) async for seq, data in store.read("nonexistent")]
    assert results == []


async def test_jsonl_store_multiple_events(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path)
    for i in range(3):
        await store.append("stream", f'{{"i":{i}}}'.encode())
    results = [(seq, data) async for seq, data in store.read("stream")]
    assert len(results) == 3


async def test_jsonl_store_from_seq(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path)
    for i in range(5):
        await store.append("stream", f'{{"i":{i}}}'.encode())
    results = [(seq, data) async for seq, data in store.read("stream", from_seq=2)]
    assert len(results) == 3


async def test_jsonl_store_stream_name_sanitization(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path)
    await store.append("market/prices:btc", b'{"p":"100"}')
    results = [(seq, data) async for seq, data in store.read("market/prices:btc")]
    assert len(results) == 1
