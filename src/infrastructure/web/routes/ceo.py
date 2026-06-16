# Layer 3 — Infrastructure (web/routes/ceo)
"""CEO executive reporting endpoints (Production Migration). Returns 503 with an
explicit reason if the CEO agent is not yet running — NEVER fabricates data."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from infrastructure.web._helpers import (
    agent_report_to_dict,
    check_api_key,
    configured_api_key,
    decision_record_to_dict,
    executive_summary_to_dict,
)
from orchestration.runtime import PipelineRuntime


def register(app: FastAPI, runtime: PipelineRuntime) -> None:
    @app.get("/api/ceo/summary")
    async def ceo_summary(request: Request) -> dict[str, object]:
        """Top-level executive view. Returns 503 with explicit reason if CEO
        agent is not yet running — NEVER fabricates data (Production rule)."""
        if configured_api_key(runtime):
            check_api_key(request, runtime)
        ceo = runtime.ceo
        if ceo is None:
            raise HTTPException(
                status_code=503,
                detail="CEO agent not initialized — runtime has not started",
            )
        es = ceo.executive_summary()
        return executive_summary_to_dict(es)

    @app.get("/api/ceo/audit")
    async def ceo_audit(
        request: Request,
        limit: int = 100,
        agent: str | None = None,
        action: str | None = None,
    ) -> dict[str, object]:
        """Replayable audit trail. Answers
        'เกิดอะไรขึ้น / ใครตัดสินใจ / ตัดสินใจจากข้อมูลอะไร / ผลลัพธ์เป็นอย่างไร'."""
        if configured_api_key(runtime):
            check_api_key(request, runtime)
        ceo = runtime.ceo
        if ceo is None:
            raise HTTPException(status_code=503, detail="CEO agent not initialized")
        from domain.audit.decision_log import AuditFilter  # noqa: PLC0415

        flt = AuditFilter(agent=agent, action=action) \
            if (agent or action) else None
        view = ceo.audit_view(flt)
        recent = view.what_happened(limit=max(1, min(limit, 1000)))
        return {
            "total_count": view.total_count,
            "by_agent": [{"agent": a, "count": c} for a, c in view.by_agent],
            "by_outcome": [{"outcome": o.value, "count": c} for o, c in view.by_outcome],
            "records": [decision_record_to_dict(r) for r in recent],
        }

    @app.get("/api/ceo/agents")
    async def ceo_agents(request: Request) -> dict[str, object]:
        """Per-agent health + role view for the CEO dashboard tab."""
        if configured_api_key(runtime):
            check_api_key(request, runtime)
        ceo = runtime.ceo
        if ceo is None:
            raise HTTPException(status_code=503, detail="CEO agent not initialized")
        es = ceo.executive_summary()
        return {
            "ts_ms": es.ts_ms,
            "agents": [agent_report_to_dict(a) for a in es.agents],
        }

    @app.get("/api/agents/learning")
    async def agents_learning(request: Request, limit: int = 40) -> dict[str, object]:
        """Self-improvement view: per-agent daily score, real accuracy, and a
        merged real-time learning feed (every entry is a real, timestamped
        event — never fabricated)."""
        return runtime.learning_overview(max(1, min(limit, 200)))
