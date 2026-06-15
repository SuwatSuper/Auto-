# Layer 3 — Infrastructure (web/routes/control)
"""Operator control-plane routes (dashboard-driven, live): mode/agent lifecycle,
emergency stop, risk settings, circuit breaker, execution mode, manual orders,
positions, alerts, login, and credential connection. All require the API key."""
from __future__ import annotations

import hmac

from fastapi import FastAPI, HTTPException, Request

from infrastructure.web._helpers import (
    check_api_key,
    check_api_key_strict,
    configured_api_key,
)
from orchestration.runtime import PipelineRuntime


def register(app: FastAPI, runtime: PipelineRuntime) -> None:
    @app.post("/api/mode/{mode}")
    async def switch_mode(mode: str, request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        # Production migration: simulator/paper/demo modes were removed.
        # The endpoint is retained for API stability — clients sending
        # "live" get an OK; everything else gets a clear 400.
        if mode != "live":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"mode {mode!r} is not supported — this build runs in 'live' "
                    "mode only (simulator/paper/demo removed in Production Migration)"
                ),
            )
        return {"ok": True, "mode": "live"}

    @app.post("/api/agents/{name}/start")
    async def start_agent(name: str, request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        await runtime.start_agent(name)
        return {"ok": True}

    @app.post("/api/agents/{name}/stop")
    async def stop_agent(name: str, request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        await runtime.stop_agent(name)
        return {"ok": True}

    @app.post("/api/agents/start_all")
    async def start_all(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        for name in runtime.agents:
            await runtime.start_agent(name)
        return {"ok": True}

    @app.post("/api/agents/stop_all")
    async def stop_all(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        for name in runtime.agents:
            await runtime.stop_agent(name)
        return {"ok": True}

    @app.post("/api/emergency_stop")
    async def emergency_stop(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        await runtime.emergency_stop()
        return {"ok": True}

    @app.post("/api/emergency_reset")
    async def emergency_reset(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        await runtime.emergency_reset()
        return {"ok": True}

    # ── Operator control plane (dashboard-driven, live) ─────────────────
    @app.get("/api/risk/settings")
    async def get_risk_settings(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        return {"ok": True, "settings": runtime.get_risk_settings()}

    @app.post("/api/risk/settings")
    async def post_risk_settings(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        try:
            patch = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body") from None
        if not isinstance(patch, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        ok, payload = await runtime.update_risk_settings(patch)
        if not ok:
            raise HTTPException(status_code=400, detail=payload.get("errors", "invalid"))
        return {"ok": True, **payload}

    @app.post("/api/breaker/trip")
    async def post_breaker_trip(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        reason = "MANUAL"
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("reason"):
                reason = str(body["reason"])
        except Exception:
            pass
        return runtime.trip_breaker(reason)

    @app.post("/api/breaker/reset")
    async def post_breaker_reset(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        try:
            body = await request.json()
            token = str(body.get("token", "")) if isinstance(body, dict) else ""
        except Exception:
            token = ""
        result = runtime.reset_breaker(token)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail="invalid reset token")
        return result

    @app.get("/api/execution/mode")
    async def get_execution_mode(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        return {"ok": True, **runtime.get_execution_mode()}

    @app.post("/api/execution/mode")
    async def post_execution_mode(request: Request) -> dict[str, object]:
        check_api_key_strict(request, runtime)  # dangerous: arms live trading
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body") from None
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        mode = str(body.get("mode", ""))
        confirm = str(body.get("confirm", ""))
        ok, payload = runtime.set_execution_mode(mode, confirm)
        if not ok:
            raise HTTPException(status_code=400, detail=payload)
        return {"ok": True, **payload}

    @app.get("/api/control/audit")
    async def get_control_audit(request: Request, limit: int = 100) -> dict[str, object]:
        check_api_key(request, runtime)
        return {"ok": True, "records": runtime.control_audit(limit)}

    @app.post("/api/order")
    async def post_order(request: Request) -> dict[str, object]:
        check_api_key_strict(request, runtime)  # dangerous: places a real order
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body") from None
        if not isinstance(body, dict) or "side" not in body:
            raise HTTPException(status_code=400, detail="body needs {side, price?}")
        ok, payload = await runtime.manual_order(str(body["side"]), body.get("price"))
        if not ok:
            raise HTTPException(status_code=400, detail=payload)
        return {"ok": True, **payload}

    @app.post("/api/positions/close")
    async def post_close(request: Request) -> dict[str, object]:
        check_api_key_strict(request, runtime)  # dangerous: closes a real position
        price = None
        try:
            body = await request.json()
            if isinstance(body, dict):
                price = body.get("price")
        except Exception:
            pass
        ok, payload = await runtime.manual_order("CLOSE", price)
        if not ok:
            raise HTTPException(status_code=400, detail=payload)
        return {"ok": True, **payload}

    @app.post("/api/positions/close_all")
    async def post_close_all(request: Request) -> dict[str, object]:
        check_api_key_strict(request, runtime)  # dangerous: flattens real positions
        return await runtime.close_all()

    @app.post("/api/alerts/test")
    async def post_alert_test(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        delivered = await runtime.send_alert("✅ Kingdom Prime test alert", "info")
        return {"ok": True, "delivered": delivered}

    @app.post("/api/login")
    async def post_login(request: Request) -> dict[str, object]:
        """Exchange the operator password for the control token (the API key)."""
        raw = getattr(runtime.settings, "dashboard_password", None)
        secret = getattr(raw, "get_secret_value", None)
        expected = secret() if callable(secret) else (str(raw) if raw else "")
        if not expected:
            raise HTTPException(status_code=400, detail="login not configured")
        try:
            body = await request.json()
            provided = str(body.get("password", "")) if isinstance(body, dict) else ""
        except Exception:
            provided = ""
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="invalid password")
        return {"ok": True, "token": configured_api_key(runtime)}

    @app.get("/api/credentials/status")
    async def get_credentials_status(request: Request) -> dict[str, object]:
        check_api_key(request, runtime)
        return {"ok": True, **runtime.account_status()}

    @app.post("/api/credentials")
    async def post_credentials(request: Request) -> dict[str, object]:
        """Set the Bitkub API key/secret from the dashboard and connect the real
        account live (no restart). The key is stored in .env and never returned."""
        check_api_key_strict(request, runtime)  # dangerous: sets real API keys
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body") from None
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        api_key = str(body.get("api_key", "")).strip()
        api_secret = str(body.get("api_secret", "")).strip()
        if not api_key or not api_secret:
            raise HTTPException(status_code=400, detail="api_key and api_secret required")
        result = await runtime.connect_account(api_key, api_secret)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "failed"))
        return result
