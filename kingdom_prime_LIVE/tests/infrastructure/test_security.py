"""Security tests: verify secrets never appear in logs or HTML output.

TASK 7: Acceptance criteria:
- Unauthenticated request to /api/status with real account connected → 401.
- API key / secret values never appear in log output (SecretStr).
- Dashboard HTML never contains the raw API secret.
"""
from __future__ import annotations

import pytest

from infrastructure.config import Settings


def test_bitkub_api_secret_is_secret_str() -> None:
    """bitkub_api_secret must be SecretStr — its repr never exposes the value."""
    from pydantic import SecretStr

    settings = Settings(bitkub_api_key="my_key", bitkub_api_secret="my_secret")  # type: ignore[call-arg]
    assert isinstance(settings.bitkub_api_secret, SecretStr)
    # repr / str must NOT contain the actual secret
    assert "my_secret" not in str(settings.bitkub_api_secret)
    assert "my_secret" not in repr(settings.bitkub_api_secret)


def test_dashboard_api_key_is_secret_str() -> None:
    """dashboard_api_key must be SecretStr."""
    from pydantic import SecretStr

    settings = Settings(dashboard_api_key="super_secret_key")  # type: ignore[call-arg]
    assert isinstance(settings.dashboard_api_key, SecretStr)
    assert "super_secret_key" not in str(settings.dashboard_api_key)


def test_secret_not_leaked_via_structlog(capfd: pytest.CaptureFixture[str]) -> None:
    """Logging a Settings object must not emit the raw secret."""
    import structlog

    settings = Settings(bitkub_api_key="LEAK_TEST_KEY", bitkub_api_secret="LEAK_TEST_SECRET")  # type: ignore[call-arg]
    log = structlog.get_logger()
    log.info("settings_snapshot", settings=str(settings))
    captured = capfd.readouterr()
    assert "LEAK_TEST_SECRET" not in captured.out
    assert "LEAK_TEST_SECRET" not in captured.err


@pytest.mark.asyncio
async def test_status_endpoint_requires_auth_when_account_connected() -> None:
    """When bitkub_account_connected=True and a dashboard key is set, /api/status → 401
    without the correct key."""
    from unittest.mock import MagicMock

    from starlette.testclient import TestClient

    from infrastructure.web.api import create_app
    from tests.conftest import make_test_runtime

    # Build runtime and start it; set _rest_gateway AFTER start() so it
    # is not overwritten by _make_agents() which resets it to None.
    rt = make_test_runtime(dashboard_api_key="test_key_abc")
    await rt.start("live")
    rt._rest_gateway = MagicMock()  # simulate a connected account
    try:
        app = create_app(rt)
        client = TestClient(app, raise_server_exceptions=False)
        # No key: should get 401 because account is connected + key configured
        resp = client.get("/api/status")
        assert resp.status_code == 401, (
            f"Expected 401 when account connected + key configured, got {resp.status_code}"
        )
        # Correct key: should get 200
        resp_ok = client.get("/api/status", headers={"x-api-key": "test_key_abc"})
        assert resp_ok.status_code == 200
    finally:
        await rt.stop()
