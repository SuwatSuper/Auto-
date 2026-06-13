# Layer 2 — Orchestration (tests/orchestration/test_live_account_wiring)
"""Phase A wiring: real-account READ-ONLY connection via reconciliation.

Verifies:
  * No API key  -> no reconciliation agent, no gateway (paper-only preserved).
  * API key set -> reconciliation agent built, real balances surface in status.
  * build_live_gateway() returns a gateway carrying the supplied credentials.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog
from pydantic import SecretStr

from infrastructure.config import Settings
from orchestration.agents.execution_agent import build_live_gateway
from orchestration.runtime import PipelineRuntime


def _runtime(settings: Settings) -> PipelineRuntime:
    return PipelineRuntime(settings=settings, logger=structlog.get_logger("test"))


def test_no_key_means_paper_only() -> None:
    """Without BITKUB_API_KEY the runtime builds no live reconciliation."""
    rt = _runtime(Settings(bitkub_api_key=SecretStr(""), persist_state=False))
    agents = rt._make_agents()
    assert "reconciliation" not in agents
    assert rt._reconciliation is None
    assert rt._rest_gateway is None


def test_key_builds_reconciliation_agent() -> None:
    """With a key present the reconciliation agent + gateway are wired."""
    rt = _runtime(
        Settings(
            bitkub_api_key=SecretStr("pub-key"),
            bitkub_api_secret=SecretStr("sec-key"),
            persist_state=False,
        )
    )
    agents = rt._make_agents()
    assert "reconciliation" in agents
    assert rt._reconciliation is not None
    assert rt._rest_gateway is not None


def test_status_reports_connection_and_balances() -> None:
    """status() exposes connection flag + last polled real balances."""
    rt = _runtime(
        Settings(
            bitkub_api_key=SecretStr("pub-key"),
            bitkub_api_secret=SecretStr("sec-key"),
            persist_state=False,
        )
    )
    rt._make_agents()
    # Simulate a completed first reconciliation poll.
    recon = rt._reconciliation
    assert recon is not None
    recon._reconciled = True  # type: ignore[attr-defined]
    recon.last_balances = {"THB": "1234.56", "BTC": "0.001"}  # type: ignore[attr-defined]

    status = rt.status()
    assert status["bitkub_account_connected"] is True
    assert status["bitkub_reconciled"] is True
    assert status["bitkub_balances"] == {"THB": "1234.56", "BTC": "0.001"}
    # Execution stays simulated regardless of account connection.
    assert status["execution_engine"] == "paper"


def test_build_live_gateway_carries_credentials() -> None:
    """The factory returns a gateway holding the provided SecretStr secret."""
    gw = build_live_gateway(SecretStr("my-key"), SecretStr("my-secret"))
    # Gateway signs with the secret; confirm it round-trips without leaking.
    assert gw._api_key.get_secret_value() == "my-key"  # type: ignore[attr-defined]
    assert gw._api_secret.get_secret_value() == "my-secret"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_balance_source_reads_via_gateway() -> None:
    """BitkubBalanceSource converts wallet values to Decimal, dropping zeros."""
    from infrastructure.gateway.bitkub_balance import BitkubBalanceSource

    class _FakeGateway:
        async def get_wallet(self) -> dict[str, object]:
            return {"THB": "500.25", "BTC": "0.01", "ETH": "0"}

    src = BitkubBalanceSource(_FakeGateway())
    balances = await src.get_balance()
    assert balances == {"THB": Decimal("500.25"), "BTC": Decimal("0.01")}
