# Tests — H1: the control plane rejects cross-site state-changing requests
# (CSRF defense) even on loopback, while leaving non-browser clients and the
# same-origin dashboard unaffected. Safe methods (GET) are never gated.
from __future__ import annotations

import structlog
from starlette.testclient import TestClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def _client(tmp_path: object, monkeypatch: object) -> TestClient:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    return TestClient(create_app(rt))


def test_cross_site_post_is_blocked(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/kill_switch",
        json={"on": True},
        headers={"Origin": "https://evil.example.com", "Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403  # CSRF blocked before any auth/handler


def test_cross_origin_simple_request_is_blocked(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c = _client(tmp_path, monkeypatch)
    # A "simple request" (no Sec-Fetch-Site) still carries a mismatched Origin.
    r = c.post("/api/kill_switch", json={"on": True}, headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_non_browser_post_passes_csrf(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c = _client(tmp_path, monkeypatch)
    # No Origin / Sec-Fetch-Site (curl, the bot's own scripts, the test client):
    # CSRF must NOT block it (it gets through to the normal auth path).
    r = c.post("/api/kill_switch", json={"on": False})
    assert r.status_code != 403


def test_safe_method_is_exempt(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c = _client(tmp_path, monkeypatch)
    # A GET never changes state, so a cross-site Origin must not block it.
    r = c.get("/api/status", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 200
