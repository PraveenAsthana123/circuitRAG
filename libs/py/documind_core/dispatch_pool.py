"""DispatchPool - fanout 100+ tasks with bounded LLM concurrency.

The AgentBoard pattern handles ONE task with N authors, K reviewers,
1 advisor running in parallel. DispatchPool handles N TASKS, each
potentially spawning its own work, with a single shared semaphore
capping the union of in-flight calls across all tasks.

Use cases:
  - Review 100 files in a PR; each file goes through an AgentBoard.
  - Re-classify 1000 historical events through a new advisor model.
  - Run a bulk eval over a corpus of 200 known-answer queries.

Why not just asyncio.gather([agent_board.run(t) for t in 100_tasks]):

  * Every AgentBoard has its own internal max_parallel semaphore.
    Without a pool-level cap, 100 boards each running 4 in parallel
    = 400 LLM calls in flight. The provider rate-limits or rejects.
  * Per-task error isolation: one task raising in gather() cancels
    the rest. The pool wraps each task in try/except so a bad task
    surfaces as an error in its slot, siblings keep running.
  * Submission-order results: gather() preserves order, but only
    if you DON'T use as_completed. The pool sorts by submission
    index regardless of completion order.

Composes with:
  * AgentBoard (libs/py/documind_core/agent_board.py) - pass each
    task to a fresh board.run() inside a worker_fn.
  * Sidecar Advisor council (services/sidecar-advisor/council.py)
    - bulk PR review across N files.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")  # task input type
R = TypeVar("R")  # task result type


@dataclass(frozen=True)
class TaskResult(Generic[T, R]):
    """One task's outcome. ``error`` is non-None if the worker_fn
    raised; ``result`` is then the type's zero-equivalent (None for
    most types). Submission order preserved via ``index``."""

    index: int           # submission index, NOT completion order
    task: T
    result: R | None
    error: str | None = None
    duration_s: float = 0.0


@dataclass
class PoolStats:
    """Aggregate stats from a single dispatch_all() invocation."""

    submitted: int
    completed: int
    failed: int
    duration_s: float
    peak_in_flight: int = 0
    failed_indices: list[int] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.submitted == 0:
            return 0.0
        return self.completed / self.submitted


class DispatchPool(Generic[T, R]):
    """Bounded-concurrency task pool.

    Args:
        worker_fn: async callable that takes one task input and
            returns one result. Wrap an AgentBoard.run() here for
            agent dispatch. The pool tracks per-task duration +
            captures exceptions per-task so siblings continue.
        max_parallel: cap on simultaneously-running workers across
            ALL submitted tasks. Set high (50-200) for tasks that
            are mostly local CPU + I/O; set low (2-8) for tasks
            that hit a rate-limited LLM provider.
        per_task_timeout_s: optional per-task deadline. None = no
            cap (worker_fn handles its own timeout).

    Usage:
        async def review_file(path):
            return await agent_board.run(open(path).read())

        pool = DispatchPool(worker_fn=review_file, max_parallel=8)
        results, stats = await pool.dispatch_all([
            "src/auth.py", "src/api.py", ... (100+ files)
        ])
    """

    def __init__(
        self,
        *,
        worker_fn: Callable[[T], Awaitable[R]],
        max_parallel: int = 8,
        per_task_timeout_s: float | None = None,
    ) -> None:
        if max_parallel < 1:
            raise ValueError(f"max_parallel must be >= 1, got {max_parallel}")
        self._worker_fn = worker_fn
        self._max_parallel = max_parallel
        self._per_task_timeout_s = per_task_timeout_s
        # In-flight tracking for the peak metric.
        self._in_flight = 0
        self._peak_in_flight = 0
        self._track_lock = asyncio.Lock()

    async def dispatch_all(
        self,
        tasks: list[T],
    ) -> tuple[list[TaskResult[T, R]], PoolStats]:
        """Submit all tasks; wait for all to complete; return results
        in submission order. NEVER raises - per-task errors are
        captured on TaskResult.error."""
        t_start = time.monotonic()
        if not tasks:
            return [], PoolStats(
                submitted=0, completed=0, failed=0, duration_s=0.0,
            )

        # Reset peak tracking per dispatch
        self._in_flight = 0
        self._peak_in_flight = 0

        sem = asyncio.Semaphore(self._max_parallel)
        coros = [
            self._run_one(idx, task, sem)
            for idx, task in enumerate(tasks)
        ]
        # gather preserves input order; we capture errors per-task
        # inside _run_one so gather itself never sees an exception.
        results: list[TaskResult[T, R]] = await asyncio.gather(*coros)
        duration = time.monotonic() - t_start

        failed_indices = [r.index for r in results if r.error is not None]
        return results, PoolStats(
            submitted=len(tasks),
            completed=len(tasks) - len(failed_indices),
            failed=len(failed_indices),
            duration_s=duration,
            peak_in_flight=self._peak_in_flight,
            failed_indices=failed_indices,
        )

    async def _run_one(
        self,
        index: int,
        task: T,
        sem: asyncio.Semaphore,
    ) -> TaskResult[T, R]:
        async with sem:
            # Track in-flight count for the peak metric. Lock guards
            # the read-modify-write; without it Python's GIL still
            # might interleave the two ops in async land.
            async with self._track_lock:
                self._in_flight += 1
                if self._in_flight > self._peak_in_flight:
                    self._peak_in_flight = self._in_flight
            t0 = time.monotonic()
            try:
                if self._per_task_timeout_s is not None:
                    result = await asyncio.wait_for(
                        self._worker_fn(task),
                        timeout=self._per_task_timeout_s,
                    )
                else:
                    result = await self._worker_fn(task)
                return TaskResult(
                    index=index,
                    task=task,
                    result=result,
                    error=None,
                    duration_s=time.monotonic() - t0,
                )
            except TimeoutError:
                msg = (
                    f"TimeoutError: task exceeded "
                    f"{self._per_task_timeout_s:.1f}s"
                )
                log.warning("dispatch_pool_timeout idx=%d", index)
                return TaskResult(
                    index=index, task=task, result=None,
                    error=msg, duration_s=time.monotonic() - t0,
                )
            except Exception as exc:  # noqa: BLE001 - error contained
                log.warning(
                    "dispatch_pool_task_failed idx=%d err=%s",
                    index, exc,
                )
                return TaskResult(
                    index=index, task=task, result=None,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_s=time.monotonic() - t0,
                )
            finally:
                async with self._track_lock:
                    self._in_flight -= 1
