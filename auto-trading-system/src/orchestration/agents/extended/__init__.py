# Layer 2 — Orchestration (agents/extended)
"""Extended department agents — Phase 2 expansion.

Every agent here does REAL work on data the system already has (the live price
stream + real portfolio/treasury/breaker state). No fabricated signals: an agent
either computes from real inputs or reports that it is warming up. Agents that
need an external data source NOT yet wired (on-chain, macro, social, order book,
funding-rate) are intentionally NOT included — they are deferred until a real
source exists, per the project's no-mock-data policy.

This package was split out of a single ``extended.py`` module for
maintainability; the public surface is unchanged and re-exported here.
"""
from __future__ import annotations

from orchestration.agents.extended.base import (
    PeriodicAgent,
    PriceListenerAgent,
    RuntimeView,
)
from orchestration.agents.extended.periodic_agents import (
    ApiConnectionMonitorAgent,
    DashboardSynthesizerAgent,
    DrawdownGuardianAgent,
    DynamicPositionSizerAgent,
    FeeOptimizerAgent,
    GarbageCollectorAgent,
    LatencyPingerAgent,
    ProfitSweeperAgent,
    TaxAccountingClerkAgent,
    TrailingStopBotAgent,
)
from orchestration.agents.extended.price_agents import (
    BlackSwanDetectorAgent,
    BreakoutSpecialistAgent,
    MeanReversionAgent,
    TrendFollowerAgent,
    VolatilityOracleAgent,
)

__all__ = [
    "ApiConnectionMonitorAgent",
    "BlackSwanDetectorAgent",
    "BreakoutSpecialistAgent",
    "DashboardSynthesizerAgent",
    "DrawdownGuardianAgent",
    "DynamicPositionSizerAgent",
    "FeeOptimizerAgent",
    "GarbageCollectorAgent",
    "LatencyPingerAgent",
    "MeanReversionAgent",
    "PeriodicAgent",
    "PriceListenerAgent",
    "ProfitSweeperAgent",
    "RuntimeView",
    "TaxAccountingClerkAgent",
    "TrailingStopBotAgent",
    "TrendFollowerAgent",
    "VolatilityOracleAgent",
]
