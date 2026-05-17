# Negative drills for Iter 27 (2026-05-17): audit retention scheduler.

import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.immutable_audit_store import ImmutableAuditStore
from audit.retention_scheduler import RetentionScheduler


def _store_with_old_records(retention_days: int = 30) -> ImmutableAuditStore:
    store = ImmutableAuditStore(retention_days=retention_days)
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 1}, tenant_id="A")
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 2}, tenant_id="A")
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 3}, tenant_id="A")
    # Age the first two to past-retention.
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    store._records[0]["payload"]["created_at"] = old
    store._records[1]["payload"]["created_at"] = old
    return store


def test_run_once_purges_expired():
    store = _store_with_old_records()
    sched = RetentionScheduler(store, interval_seconds=3600)
    purged = sched.run_once()
    assert purged == 2
    assert sched.last_purge_count == 2
    assert sched.last_purge_at is not None
    assert sched.total_purged == 2
    # Chain rebuilds — verify_integrity still passes.
    assert store.verify_integrity()["valid"] is True


def test_BACKDOOR_CHECK_scheduler_fires_periodic_purges():
    """Pre-fix: retention method existed but nothing called it."""
    store = _store_with_old_records()
    sched = RetentionScheduler(store, interval_seconds=0.05)
    sched.start()
    # Wait long enough for at least 2 ticks.
    time.sleep(0.15)
    sched.stop()
    assert sched.total_purged >= 2


def test_on_purge_hook_fires_with_count():
    store = _store_with_old_records()
    counts = []
    sched = RetentionScheduler(
        store, interval_seconds=3600,
        on_purge=lambda n: counts.append(n),
    )
    sched.run_once()
    assert counts == [2]


def test_on_purge_hook_failure_does_not_break_scheduler():
    store = _store_with_old_records()
    def bad_hook(n):
        raise RuntimeError("boom")
    sched = RetentionScheduler(
        store, interval_seconds=3600, on_purge=bad_hook,
    )
    # MUST NOT raise.
    purged = sched.run_once()
    assert purged == 2
    assert sched.last_purge_count == 2


def test_stop_preempts_sleep():
    """A stop() during a long interval should return quickly."""
    store = _store_with_old_records()
    sched = RetentionScheduler(store, interval_seconds=60)
    sched.start()
    started = time.time()
    sched.stop()
    elapsed = time.time() - started
    # stop() should NOT wait 60s for the next tick.
    assert elapsed < 5.0


def test_double_start_is_idempotent():
    store = _store_with_old_records()
    sched = RetentionScheduler(store, interval_seconds=10)
    sched.start()
    sched.start()  # no error
    assert sched.is_running()
    sched.stop()


def test_constructor_rejects_too_short_interval():
    store = ImmutableAuditStore()
    with pytest.raises(ValueError):
        RetentionScheduler(store, interval_seconds=0)
    with pytest.raises(ValueError):
        RetentionScheduler(store, interval_seconds=0.001)  # under 10ms floor


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
