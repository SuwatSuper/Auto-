# Tests — set Bitkub credentials from dashboard + live connect (no network)
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


class _FakeBalance:
    async def get_balance(self) -> dict[str, Decimal]:
        return {"THB": Decimal("1234.56"), "BTC": Decimal("0.001")}


def _rt() -> PipelineRuntime:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    return rt


@pytest.mark.asyncio
async def test_connect_account_requires_both() -> None:
    rt = _rt()
    res = await rt.connect_account("", "", start_polling=False)
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_connect_account_wires_and_reports(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)  # isolate .env writes
    rt = _rt()
    res = await rt.connect_account(
        "pub-key", "sec-key", balance_source=_FakeBalance(), start_polling=True
    )
    assert res["ok"] is True
    # credentials updated on settings
    assert rt.settings.bitkub_api_key.get_secret_value() == "pub-key"
    # reconciliation agent built + reachable
    assert "reconciliation" in rt.agents
    # status reflects connection (key never leaked)
    st = rt.account_status()
    assert st["has_key"] is True and st["connected"] is True
    assert "pub-key" not in str(st)
    # .env persisted
    assert (tmp_path / ".env").exists()
    content = (tmp_path / ".env").read_text()
    assert "BITKUB_API_KEY=pub-key" in content
    await rt._disconnect_account()


@pytest.mark.asyncio
async def test_reconnect_replaces_old(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt()
    await rt.connect_account("k1", "s1", balance_source=_FakeBalance(), start_polling=False)
    await rt.connect_account("k2", "s2", balance_source=_FakeBalance(), start_polling=False)
    assert rt.settings.bitkub_api_key.get_secret_value() == "k2"
    assert "BITKUB_API_KEY=k2" in (tmp_path / ".env").read_text()
    await rt._disconnect_account()
