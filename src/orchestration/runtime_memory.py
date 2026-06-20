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
    # Task 2/3: the learned dynamic weights (per-source trade win-rate) and the
    # swarm's per-(method, regime) reliability table, so self-learning survives
    # a restart instead of starting cold every session.
    _WEIGHTS_KEY = "weights.learned.v1"
    # The circuit-breaker's tripped/streak state, persisted so a HALT survives a
    # restart — only the operator may reset it, never a silent reboot (C1).
    _BREAKER_KEY = "risk.circuit_breaker.v1"


    async def _persist_controls(self, settings: dict[str, str]) -> None:
        store = self._state_store or self._ensure_state_store()
        if store is None:
            return
        with contextlib.suppress(Exception):
            await store.set(self._CONTROL_KEY, orjson.dumps(settings))

    async def _persist_breaker(self) -> None:
        """Snapshot the circuit-breaker state to disk (best-effort, never raises).

        Wired to ``CircuitBreaker.on_change`` so EVERY trip/reset/streak change
        is durably saved. A tripped breaker therefore stays tripped across a
        restart instead of silently re-arming live trading."""
        store = self._memory_store()
        br = self._circuit_breaker
        if store is None or br is None:
            return
        with contextlib.suppress(Exception):
            await store.set(self._BREAKER_KEY, orjson.dumps(br.to_dict()))

    def _schedule_breaker_persist(self) -> None:
        """Sync hook for ``CircuitBreaker.on_change``: persist on the running loop.

        The breaker can change state from inside an async agent task (auto-trip
        on a losing streak) or an operator control call — both run with a live
        event loop, so we schedule the async write. No loop (e.g. a unit test
        constructing a bare runtime) → no-op."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._persist_breaker())

    async def _restore_breaker(self) -> None:
        """Reload the circuit-breaker tripped state from the last session so a
        halt is honoured after a restart (C1). Best-effort; never raises."""
        store = self._memory_store()
        br = self._circuit_breaker
        if store is None or br is None:
            return
        try:
            raw = await store.get(self._BREAKER_KEY)
        except Exception:
            return
        if raw is None:
            return
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return
        if isinstance(data, dict):
            br.load_dict(data)
            if br.is_open:
                self.logger.warning(
                    "runtime.breaker_restored_open",
                    consecutive_losses=br.consecutive_losses,
                )

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
        # Persist the learned dynamic weights alongside the per-agent memory.
        weights_blob = {
            "source_perf": self._source_perf.to_dict(),
            "swarm_meta": self._swarm_meta.to_dict(),
        }
        with contextlib.suppress(Exception):
            await store.set(self._WEIGHTS_KEY, orjson.dumps(weights_blob))

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
        await self._restore_weights(store)

    async def _restore_weights(self, store: StateStore) -> None:
        """Reload the learned dynamic weights (Task 2/3) and push the source
        weights into the live Supreme commander. Best-effort; never raises."""
        try:
            raw = await store.get(self._WEIGHTS_KEY)
        except Exception:
            return
        if raw is None:
            return
        try:
            blob = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return
        if not isinstance(blob, dict):
            return
        sp = blob.get("source_perf")
        if isinstance(sp, dict):
            with contextlib.suppress(Exception):
                self._source_perf.load_dict(sp)
                supreme = self.agents.get("supreme_commander")
                if supreme is not None and hasattr(supreme, "update_weights"):
                    supreme.update_weights(self._source_perf.weights())
        sm = blob.get("swarm_meta")
        if isinstance(sm, dict):
            with contextlib.suppress(Exception):
                self._swarm_meta.load_dict(sm)

    def _roll_learner_days(self) -> None:
        """Reset every learner's daily counters on a TIMER (M5).

        The daily rollover was previously driven only by building the dashboard
        status, so a headless run / idle UI across midnight left the daily
        hit-rate stale — and strategy self-tuning keys off it. Driving it from
        the memory loop makes the reset happen regardless of observation."""
        for name, agent in self.agents.items():
            with contextlib.suppress(Exception):
                self._learner_for(name, agent).roll_day()

    async def _memory_loop(self) -> None:
        """Persist memory on an interval so progress is saved gradually."""
        interval = float(getattr(self.settings, "memory_persist_interval_s", 30.0))
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            self._roll_learner_days()
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
                # from_restore=True: this is a machine reload, not an operator
                # edit — don't let it disable the Kelly auto-sizer (M9).
                await self.update_risk_settings(dict(data), from_restore=True)
