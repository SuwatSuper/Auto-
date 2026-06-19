# Tests — infra durability fixes:
#   H7  the JSONL event store skips a torn (newline-less) trailing line on read.
#   M6  SqliteStateStore.keys() escapes LIKE metacharacters so a prefix with
#       '_' / '%' matches literally.
from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.events.jsonl_store import JsonlEventStore
from infrastructure.state.sqlite_store import SqliteStateStore


@pytest.mark.asyncio
async def test_jsonl_skips_torn_trailing_line(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path)
    await store.append("s", b'{"a":1}')
    await store.append("s", b'{"a":2}')
    # Simulate a crash mid-append: a partial record with no trailing newline.
    path = tmp_path / "s.jsonl"
    with path.open("ab") as f:
        f.write(b'{"a":3')  # torn, no '\n'
    rows = [line async for _seq, line in store.read("s")]
    assert rows == [b'{"a":1}', b'{"a":2}']  # the torn tail is not yielded


@pytest.mark.asyncio
async def test_sqlite_keys_escapes_like_wildcards(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "s.db")
    await store.set("a_b.one", b"1")
    await store.set("axb.two", b"2")   # 'x' must NOT match the literal '_'
    await store.set("other", b"3")
    # '_' is a LIKE wildcard; with escaping the prefix 'a_b.' matches only the
    # literal key, not 'axb.two'.
    assert await store.keys("a_b.") == ["a_b.one"]
    store.close()
