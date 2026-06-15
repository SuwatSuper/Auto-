# Layer 2 — Orchestration (runtime/runtime_strategy)
"""T3: live strategy control — enable/disable signal-emitting strategies and tune
their parameters with REAL effect on the decision pipeline.

A disabled strategy keeps running (heartbeat/metrics) but emits no signals; a
tuned parameter changes the next signal it produces. Strategies map 1:1 to the
signal-emitting agents that feed signals.v1.

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from orchestration.agents.entry_exit import EntryExitAgent
from orchestration.agents.extended import (
    BreakoutSpecialistAgent,
    MeanReversionAgent,
    TrendFollowerAgent,
)
from orchestration.runtime_base import _RuntimeBase

# strategy id (== agent name) -> human label.
_STRATEGY_AGENTS: dict[str, str] = {
    "market_analyst": "EMA-cross entries (EmaCrossStrategy)",
    "trend_follower": "Trend follower (EMA20/50)",
    "mean_reversion": "Mean reversion (RSI)",
    "breakout_specialist": "Breakout (Donchian channel)",
}


def _params_of(agent: object) -> dict[str, str]:
    """Read the live tunable parameters of a strategy agent."""
    if isinstance(agent, EntryExitAgent | TrendFollowerAgent):
        return {"min_gap_pct": f"{agent._min_gap_pct:.4f}"}
    if isinstance(agent, MeanReversionAgent):
        return {
            "rsi_oversold": str(agent._strat.oversold),
            "rsi_overbought": str(agent._strat.overbought),
        }
    if isinstance(agent, BreakoutSpecialistAgent):
        return {"channel_n": str(agent._n)}
    return {}


def _apply_params(agent: object, patch: dict[str, object]) -> list[str]:
    """Validate + apply a parameter patch; returns a list of error strings."""
    errors: list[str] = []
    for key, raw in patch.items():
        try:
            if isinstance(agent, EntryExitAgent | TrendFollowerAgent) and key == "min_gap_pct":
                val = float(str(raw))
                if not 0.0 <= val <= 5.0:
                    errors.append(f"min_gap_pct must be 0..5 (got {val})")
                    continue
                agent._min_gap_pct = val
            elif isinstance(agent, MeanReversionAgent) and key in ("rsi_oversold", "rsi_overbought"):
                d = Decimal(str(raw))
                if not Decimal("0") <= d <= Decimal("100"):
                    errors.append(f"{key} must be 0..100 (got {d})")
                    continue
                if key == "rsi_oversold":
                    agent._strat.oversold = d
                else:
                    agent._strat.overbought = d
            elif isinstance(agent, BreakoutSpecialistAgent) and key == "channel_n":
                n = int(str(raw))
                if not 2 <= n <= 200:
                    errors.append(f"channel_n must be 2..200 (got {n})")
                    continue
                agent._n = n
            else:
                errors.append(f"unknown/invalid param {key!r} for this strategy")
        except (ValueError, InvalidOperation):
            errors.append(f"{key}: not a number ({raw!r})")
    return errors


def _is_enabled(agent: object) -> bool:
    return bool(agent.enabled) if isinstance(
        agent, EntryExitAgent | TrendFollowerAgent | MeanReversionAgent | BreakoutSpecialistAgent
    ) else True


def _set_enabled(agent: object, on: bool) -> None:
    if isinstance(
        agent, EntryExitAgent | TrendFollowerAgent | MeanReversionAgent | BreakoutSpecialistAgent
    ):
        agent.enabled = on


class _StrategyMixin(_RuntimeBase):
    def strategy_overview(self) -> list[dict[str, object]]:
        """List signal strategies with enabled state, running state, and params."""
        out: list[dict[str, object]] = []
        for sid, label in _STRATEGY_AGENTS.items():
            agent = self.agents.get(sid)
            if agent is None:
                continue
            out.append({
                "id": sid,
                "label": label,
                "enabled": _is_enabled(agent),
                "running": bool(getattr(agent, "running", False)),
                "params": _params_of(agent),
            })
        return out

    def set_strategy_enabled(self, sid: str, on: bool) -> tuple[bool, dict[str, object]]:
        agent = self.agents.get(sid)
        if sid not in _STRATEGY_AGENTS or agent is None:
            return False, {"error": f"unknown strategy {sid!r}"}
        _set_enabled(agent, bool(on))
        self._record_control("strategy_enabled", {"id": sid, "on": bool(on)})
        return True, {"id": sid, "enabled": bool(on)}

    def set_strategy_params(
        self, sid: str, patch: object
    ) -> tuple[bool, dict[str, object]]:
        agent = self.agents.get(sid)
        if sid not in _STRATEGY_AGENTS or agent is None:
            return False, {"error": f"unknown strategy {sid!r}"}
        if not isinstance(patch, dict):
            return False, {"error": "params must be a JSON object"}
        errors = _apply_params(agent, patch)
        if errors:
            return False, {"errors": errors}
        new_params = _params_of(agent)
        self._record_control("strategy_params", {"id": sid, "params": new_params})
        return True, {"id": sid, "params": new_params}
