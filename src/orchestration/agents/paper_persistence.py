# Layer 2 — Orchestration (agents/paper_persistence)
"""Crash-safe persistence for PaperTraderAgent (atomic session snapshot + legacy
fallback). Extracted from paper_trader.py so the agent stays focused; the keys
are re-exported there for backwards-compat."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import orjson

from domain.trading.paper import PaperPosition

if TYPE_CHECKING:
    from orchestration.agents.paper_trader import PaperTraderAgent

_POSITION_KEY = "paper.position.v1"
_SESSION_KEY = "paper.session.v1"


def treasury_snapshot(a: PaperTraderAgent) -> dict[str, object]:
    t = a._treasury
    return {
        "cash": str(t.cash),
        "realized_pnl": str(t.realized_pnl),
        "realized_today": str(t.realized_today),
        "day_key": t.day_key,
        "wins": t.wins,
        "losses": t.losses,
        "halted": t.halted,
    }

async def load_state(a: PaperTraderAgent) -> None:
    if a._store is None:
        return
    # Try combined atomic key first (crash-safe)
    raw = await a._store.get(_SESSION_KEY)
    if raw is not None:
        try:
            data = orjson.loads(raw)
            a._session_seq = int(data.get("seq", 0))
            pos_data = data.get("position")
            if pos_data is not None:
                a.position = PaperPosition.model_validate(pos_data)
            a.trades_closed = int(data.get("trades_closed", 0))
            a.entries_opened = int(data.get("entries_opened", 0))
            a._position_is_live = bool(data.get("position_is_live", False))
            # Restore treasury from the same snapshot
            t_data = data.get("treasury")
            if t_data:
                a._treasury.cash = Decimal(str(t_data["cash"]))
                a._treasury.realized_pnl = Decimal(str(t_data["realized_pnl"]))
                a._treasury.realized_today = Decimal(str(t_data["realized_today"]))
                a._treasury.day_key = str(t_data["day_key"])
                a._treasury.wins = int(t_data["wins"])
                a._treasury.losses = int(t_data["losses"])
                a._treasury.halted = bool(t_data["halted"])
            a.state_loaded = True
            a._treasury._session_loaded = True
            a._log.info("paper_trader.session_restored", open=a.position is not None)
            return
        except (orjson.JSONDecodeError, KeyError, ValueError, Exception):
            a._log.warning("paper_trader.session_corrupt_ignored", exc_info=True)

    # Backward-compat: fall back to legacy split keys
    raw = await a._store.get(_POSITION_KEY)
    if raw is None:
        return
    try:
        data = orjson.loads(raw)
        pos_data = data.get("position")
        if pos_data is not None:
            a.position = PaperPosition.model_validate(pos_data)
        a.trades_closed = int(data.get("trades_closed", 0))
        a.entries_opened = int(data.get("entries_opened", 0))
        # Consistency check: if position exists, verify cash doesn't exceed initial capital
        # (legacy state may be inconsistent — drop phantom position, keep cash)
        if a.position is not None and a._treasury.cash >= a._treasury._limits.initial_capital:
            a._log.warning(
                "state.inconsistent_repaired",
                reason="position_with_full_cash",
            )
            a.position = None
        a.state_loaded = True
        a._log.info("paper_trader.state_restored", open=a.position is not None)
    except (orjson.JSONDecodeError, KeyError, ValueError):
        a._log.warning("paper_trader.state_corrupt_ignored", exc_info=True)

async def save_state(a: PaperTraderAgent) -> None:
    if a._store is None:
        return
    a._session_seq += 1
    pos = None
    if a.position is not None:
        pos = orjson.loads(a.position.model_dump_json())
    payload = orjson.dumps(
        {
            "seq": a._session_seq,
            "treasury": treasury_snapshot(a),
            "position": pos,
            "position_is_live": a._position_is_live,
            "trades_closed": a.trades_closed,
            "entries_opened": a.entries_opened,
        }
    )
    await a._store.set(_SESSION_KEY, payload)
