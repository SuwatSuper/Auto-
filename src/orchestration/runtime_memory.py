# Layer 2 — Orchestration (runtime/runtime_memory)
"""Durable memory + control persistence for PipelineRuntime.

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

import asyncio
import contextlib

import orjson

from orchestration.ports.state_store import StateStore
from orchestration.runtime_base import _RuntimeBase


class _MemoryMixin(_RuntimeBase):
    _CONTROL_KEY = "control.settings.v1"
    _MEMORY_KEY = "agents.memory.v1"  # every agent's learned memory, on disk


    async def _persist_controls(self, settings: dict[str, str]) -> None:
        store = self._state_store or self._ensure_state_store()
        if store is None:
            return
        with contextlib.suppress(Exception):
            await store.set(self._CONTROL_KEY, orjson.dumps(settings))

    def _memory_store(self) -> StateStore | None:
        """The state store used for agent memory (SQLite on disk in prod)."""
        return self._state_store or self._ensure_state_store()

    async def _persist_memories(self) -> None:
        """Write every agent's Learner memory (counters + mistakes/fixes journal)
        to the state store as one atomic snapshot. Best-effort; never raises."""
        store = self._memory_store()
        if store is None:
            return
        payload: dict[str, object] = {
            name: self._learner_for(name, agent).to_dict()
            for name, agent in self.agents.items()
        }
        with contextlib.suppress(Exception):
            await store.set(self._MEMORY_KEY, orjson.dumps(payload))

    async def _restore_memories(self) -> None:
        """Reload each agent's memory from the last session so it remembers its
        past mistakes and the fixes it made (ความทรงจำจากของเดิม)."""
        store = self._memory_store()
        if store is None:
            return
        try:
            raw = await store.get(self._MEMORY_KEY)
        except Exception:
            return
        if raw is None:
            return
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        restored = 0
        for name, agent in self.agents.items():
            mem = data.get(name)
            if not isinstance(mem, dict):
                continue
            learner = self._learner_for(name, agent)
            learner.load_dict(mem)
            learner.log("🧠 จำจากเซสชันก่อนได้ (ความผิดพลาด + การแก้ไข)", "event")
            restored += 1
        self.logger.info("runtime.memory_restored", agents=restored)

    async def _memory_loop(self) -> None:
        """Persist memory on an interval so progress is saved gradually."""
        interval = float(getattr(self.settings, "memory_persist_interval_s", 30.0))
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            await self._persist_memories()

    async def load_controls(self) -> None:
        """Restore persisted control settings on startup (best-effort)."""
        store = self._state_store or self._ensure_state_store()
        if store is None:
            return
        try:
            raw = await store.get(self._CONTROL_KEY)
        except Exception:
            return
        if raw is None:
            return
        with contextlib.suppress(Exception):
            data = orjson.loads(raw)
            if isinstance(data, dict):
                await self.update_risk_settings(dict(data))
