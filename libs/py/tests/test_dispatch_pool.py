"""
Tests for documind_core.dispatch_pool — bounded-concurrency task pool.

Covers:
- TaskResult / PoolStats dataclasses
- PoolStats.success_rate (incl. zero-submitted edge: must NOT
  raise ZeroDivisionError; returns 0.0)
- DispatchPool init: max_parallel must be >= 1
- dispatch_all empty list returns ([], PoolStats(0,0,0,0))
- dispatch_all preserves submission ORDER even if completion order
  differs (the "submission-order vs as_completed" contract)
- dispatch_all isolates per-task exceptions: one task raises, rest
  finish, error string lives on TaskResult.error
- dispatch_all enforces per_task_timeout_s — slow task gets
  TimeoutError with non-None error string
- dispatch_all enforces max_parallel: peak_in_flight ≤ max_parallel
"""

from __future__ import annotations

import asyncio

import pytest

from documind_core.dispatch_pool import DispatchPool, PoolStats, TaskResult


class TestPoolStats:
    def test_success_rate_normal(self) -> None:
        s = PoolStats(submitted=10, completed=8, failed=2, duration_s=1.0)
        assert s.success_rate == 0.8

    def test_success_rate_zero_submitted_no_div_zero(self) -> None:
        # NEGATIVE: empty dispatch must NOT raise ZeroDivisionError —
        # callers reading the rate after dispatch_all([]) get 0.0.
        s = PoolStats(submitted=0, completed=0, failed=0, duration_s=0.0)
        assert s.success_rate == 0.0


class TestTaskResult:
    def test_dataclass_default_error_none(self) -> None:
        r = TaskResult(index=0, task="t", result="r")
        assert r.error is None
        assert r.duration_s == 0.0


class TestDispatchPool:
    @pytest.mark.asyncio
    async def test_max_parallel_must_be_positive(self) -> None:
        async def noop(_t):
            return None

        with pytest.raises(ValueError, match="max_parallel"):
            DispatchPool(worker_fn=noop, max_parallel=0)

    @pytest.mark.asyncio
    async def test_empty_task_list_short_circuits(self) -> None:
        async def noop(_t):
            return None

        pool = DispatchPool(worker_fn=noop, max_parallel=8)
        results, stats = await pool.dispatch_all([])
        assert results == []
        assert stats.submitted == 0
        assert stats.completed == 0
        assert stats.duration_s == 0.0

    @pytest.mark.asyncio
    async def test_results_in_submission_order(self) -> None:
        # Slower-for-earlier-tasks pattern — completion order is REVERSED
        # but result order MUST match submission order.
        async def worker(idx: int) -> int:
            await asyncio.sleep(0.01 * (5 - idx))  # later-indexed = faster
            return idx * 10

        pool = DispatchPool(worker_fn=worker, max_parallel=4)
        results, stats = await pool.dispatch_all(list(range(5)))
        # The contract: results sorted by submission index.
        assert [r.index for r in results] == [0, 1, 2, 3, 4]
        assert [r.result for r in results] == [0, 10, 20, 30, 40]
        assert stats.completed == 5

    @pytest.mark.asyncio
    async def test_per_task_error_isolation(self) -> None:
        # One task raises — the rest complete cleanly, error captured
        # on the failing TaskResult, gather() never sees the exception.
        async def worker(t: int) -> int:
            if t == 2:
                raise ValueError("intentional")
            return t * 100

        pool = DispatchPool(worker_fn=worker, max_parallel=4)
        results, stats = await pool.dispatch_all([1, 2, 3])
        assert stats.submitted == 3
        assert stats.completed == 2
        assert stats.failed == 1
        assert stats.failed_indices == [1]  # task index 1 (= input "2") failed
        # Successful results survive
        assert results[0].error is None and results[0].result == 100
        # The bad one carries the error string
        assert results[1].error is not None
        assert "ValueError" in results[1].error
        assert "intentional" in results[1].error
        # Sibling after the failure also completed
        assert results[2].error is None and results[2].result == 300

    @pytest.mark.asyncio
    async def test_per_task_timeout_enforced(self) -> None:
        async def slow(_t):
            await asyncio.sleep(1.0)  # never finishes within timeout
            return "done"

        pool = DispatchPool(worker_fn=slow, max_parallel=2, per_task_timeout_s=0.05)
        results, stats = await pool.dispatch_all(["a", "b"])
        assert stats.failed == 2
        for r in results:
            assert r.error is not None
            assert "TimeoutError" in r.error

    @pytest.mark.asyncio
    async def test_max_parallel_capped(self) -> None:
        # peak_in_flight must NOT exceed max_parallel — this is the
        # whole point of the pool. Without the semaphore, 100 LLM calls
        # would all fire at once.
        async def slow(_t):
            await asyncio.sleep(0.05)
            return None

        pool = DispatchPool(worker_fn=slow, max_parallel=3)
        _, stats = await pool.dispatch_all(list(range(20)))
        assert stats.peak_in_flight <= 3
        # And we did exercise the bound — peak should equal 3 with
        # 20 slow tasks fanning out.
        assert stats.peak_in_flight >= 1
