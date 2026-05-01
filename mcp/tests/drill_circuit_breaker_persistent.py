#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-F-big — persistent breaker state across instance lifetimes (#21).

Locks the multi-pod deployment safety net: when a service restarts
during an outage, the new process must come back in the LAST KNOWN
state (OPEN if the downstream was broken), not CLOSED. Otherwise all
N pods immediately retry the dead downstream → cascade returns.

Negative assertions:
  - Stale snapshot (older than max_age_s) is IGNORED — a writer that
    died doesn't lock a frozen state forever.
  - Persistent store failures don't crash the breaker.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load() -> object:
    sys.path.insert(0, str(REPO / "libs" / "py"))
    import documind_core.circuit_breaker as cb  # noqa: PLC0415
    return cb


def main() -> int:
    cb_mod = _load()
    CircuitBreaker = cb_mod.CircuitBreaker
    State = cb_mod.State
    InMemoryPersistentStore = cb_mod.InMemoryPersistentStore
    BreakerSnapshot = cb_mod.BreakerSnapshot

    print("-- 1. POSITIVE: PersistentBreakerStore Protocol + InMemoryPersistentStore exported --")
    assert hasattr(cb_mod, "PersistentBreakerStore")
    assert hasattr(cb_mod, "InMemoryPersistentStore")
    assert hasattr(cb_mod, "BreakerSnapshot")
    print("  ok: 3 new public symbols")

    # -------------------------------------------------------------
    # FIX #21a: hydration from snapshot
    # -------------------------------------------------------------
    print("-- 2. POSITIVE: breaker hydrates OPEN state from store --")
    store = InMemoryPersistentStore(max_age_s=60)
    # Pre-populate: simulate a prior instance saved OPEN state.
    store.save_snapshot(
        name="hydration",
        tenant_id=None,
        snapshot=BreakerSnapshot(
            state="open",
            opened_at=0.0,  # not used by hydrator
            consecutive_open_count=2,
            failure_count=5,
            wall_clock_recorded_at=time.time(),  # fresh
        ),
    )
    cb = CircuitBreaker("hydration", persistent_store=store)
    assert cb.state is State.OPEN, (
        f"FIX #21 BROKEN: failed to hydrate OPEN; got {cb.state}"
    )
    assert cb._consecutive_open_count == 2
    assert cb._failure_count == 5
    print(f"  ok: hydrated state=OPEN, consecutive_opens=2, failures=5")

    # -------------------------------------------------------------
    # FIX #21b: stale snapshot is ignored
    # -------------------------------------------------------------
    print("-- 3. NEGATIVE: stale snapshot (>max_age_s) is ignored --")
    store_strict = InMemoryPersistentStore(max_age_s=0.05)
    store_strict.save_snapshot(
        name="stale",
        tenant_id=None,
        snapshot=BreakerSnapshot(
            state="open",
            opened_at=0.0,
            consecutive_open_count=99,
            failure_count=99,
            wall_clock_recorded_at=time.time() - 60,  # 60s old
        ),
    )
    cb = CircuitBreaker("stale", persistent_store=store_strict)
    assert cb.state is State.CLOSED, (
        f"FIX #21 BROKEN: stale snapshot should be ignored; got {cb.state}"
    )
    print(f"  ok: stale snapshot rejected → fresh CLOSED start")

    # -------------------------------------------------------------
    # FIX #21c: writes propagate on transition
    # -------------------------------------------------------------
    print("-- 4. POSITIVE: state transition saves snapshot --")
    import asyncio

    async def _fail() -> None:
        raise ConnectionError("down")

    store = InMemoryPersistentStore()
    cb = CircuitBreaker(
        "writes",
        failure_threshold=1,
        persistent_store=store,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    snap = store.load_snapshot(name="writes")
    assert snap is not None
    assert snap.state == "open", f"snapshot should be OPEN; got {snap.state}"
    assert snap.consecutive_open_count == 1
    print(f"  ok: trip persisted state='{snap.state}', opens={snap.consecutive_open_count}")

    # -------------------------------------------------------------
    # FIX #21d: broken store doesn't crash the breaker
    # -------------------------------------------------------------
    print("-- 5. NEGATIVE: broken store → load failure caught + breaker starts fresh --")
    class _BrokenLoad:
        def load_snapshot(self, **_kwargs):
            raise RuntimeError("redis down")
        def save_snapshot(self, **_kwargs):
            pass

    cb = CircuitBreaker("load-failed", persistent_store=_BrokenLoad())
    assert cb.state is State.CLOSED, "broken loader → fresh CLOSED start"
    print("  ok: broken load → caught + logged + fresh start")

    print("-- 6. NEGATIVE: broken store → save failure caught + breaker keeps working --")
    class _BrokenSave:
        def load_snapshot(self, **_kwargs):
            return None
        def save_snapshot(self, **_kwargs):
            raise RuntimeError("redis save failed")

    cb = CircuitBreaker(
        "save-failed",
        failure_threshold=1,
        persistent_store=_BrokenSave(),
    )
    # Trip → save would fail, but breaker should still trip locally.
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN, (
        f"FIX #21 BROKEN: broken save crashed breaker; got {cb.state}"
    )
    print("  ok: broken save → breaker still trips locally")

    # -------------------------------------------------------------
    # FIX #21e: persistent_store=None preserves legacy
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: persistent_store=None preserves legacy single-process --")
    cb = CircuitBreaker("legacy")
    assert cb.persistent_store is None
    print("  ok: persistent_store defaults None")

    # -------------------------------------------------------------
    # FIX #21f: tenant scope isolated in store
    # -------------------------------------------------------------
    print("-- 8. NEGATIVE: tenant_a snapshot does NOT hydrate tenant_b breaker --")
    store = InMemoryPersistentStore()
    store.save_snapshot(
        name="multi-tenant",
        tenant_id="tenant_a",
        snapshot=BreakerSnapshot(
            state="open", opened_at=0.0,
            consecutive_open_count=3, failure_count=5,
            wall_clock_recorded_at=time.time(),
        ),
    )
    cb_a = CircuitBreaker("multi-tenant", tenant_id="tenant_a", persistent_store=store)
    cb_b = CircuitBreaker("multi-tenant", tenant_id="tenant_b", persistent_store=store)
    assert cb_a.state is State.OPEN
    assert cb_b.state is State.CLOSED, (
        "tenant_b should NOT inherit tenant_a's state"
    )
    print("  ok: tenant scope isolated in store keys")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
