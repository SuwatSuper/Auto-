# Tests — connect_account immediate wallet verification (truthful result/error)
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


class _Ok:
    async def get_balance(self):
        return {"THB": Decimal("5000"), "BTC": Decimal("0.002")}


class _Bad:
    async def get_balance(self):
        raise RuntimeError("Bitkub API error 3: Invalid API key")


def _rt():
    rt = PipelineRuntime(settings=Settings(training_mode=False, persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    return rt


@pytest.mark.asyncio
async def test_connect_verifies_wallet_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rt = _rt()
    res = await rt.connect_account("k", "s", balance_source=_Ok(), start_polling=False)
    assert res["ok"] is True
    assert res["verified"] is True
    assert res["error"] is None
    assert res["balances"]["THB"] == "5000"
    st = rt.account_status()
    assert st["reconciled"] is True and st["last_error"] is None
    await rt._disconnect_account()


@pytest.mark.asyncio
async def test_connect_surfaces_bitkub_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rt = _rt()
    res = await rt.connect_account("k", "s", balance_source=_Bad(), start_polling=False)
    # key is saved (ok) but wallet read failed — the REAL Bitkub error is returned
    assert res["ok"] is True
    assert res["verified"] is False
    assert "Invalid API key" in res["error"]
    st = rt.account_status()
    assert st["reconciled"] is False
    assert "Invalid API key" in st["last_error"]
    await rt._disconnect_account()
