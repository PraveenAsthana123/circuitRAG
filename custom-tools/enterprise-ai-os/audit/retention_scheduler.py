# Added Iter 27 (2026-05-17) — periodic-purge scheduler for the
# ImmutableAuditStore. Pre-fix the retention policy was a method that
# nobody called; this wires it to a thread-based scheduler so a
# long-running app actually evicts expired records.
#
# Why threading and not asyncio: the audit store is sync, and the
# scheduler is independent of any async runtime. Caller starts the
# scheduler at app startup, stops it at shutdown.
#
# Real production should use a proper job runner (Celery beat, k8s
# CronJob, APScheduler with persistence) so the schedule survives
# restart. This stub closes the "purge never runs" gap.

import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from audit.immutable_audit_store import ImmutableAuditStore


class RetentionScheduler:
    """Runs ImmutableAuditStore.purge_expired() on a cadence."""

    def __init__(
        self,
        store: ImmutableAuditStore,
        interval_seconds: float = 3600.0,
        on_purge: Optional[Callable[[int], None]] = None,
    ):
        # Floor at 10ms to prevent tight-loop accidents but allow
        # tests to use sub-second cadence.
        if interval_seconds < 0.01:
            raise ValueError("interval_seconds must be >= 0.01")
        self.store = store
        self.interval_seconds = interval_seconds
        self.on_purge = on_purge
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_purge_at: Optional[datetime] = None
        self.last_purge_count: int = 0
        self.total_purged: int = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # idempotent — already running
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="audit-retention-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_once(self) -> int:
        """Synchronous single purge. Useful in tests + for caller-
        triggered cleanup outside the schedule."""
        count = self.store.purge_expired()
        self.last_purge_at = datetime.now(timezone.utc)
        self.last_purge_count = count
        self.total_purged += count
        if self.on_purge is not None:
            try:
                self.on_purge(count)
            except Exception:  # never crash the scheduler on hook failure
                pass
        return count

    def _loop(self) -> None:
        # Use Event.wait so stop() preempts the sleep.
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.run_once()
            except Exception:
                # Scheduler MUST survive a single purge failure;
                # next tick will retry.
                pass
