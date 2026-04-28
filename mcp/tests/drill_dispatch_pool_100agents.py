#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: DispatchPool fans out 100+ tasks with bounded concurrency.

Locks the contract that:

  pool.dispatch_all([100+ tasks])
    -> all complete in bounded wall-time
    -> peak in-flight respects max_parallel (NOT 100)
    -> per-task error isolation: one task raising doesn't sink siblings
    -> results returned in SUBMISSION order, NOT completion order
    -> empty submission returns immediately

Eight steps. Six negative assertions.

  1. 100 tasks at 50ms each, max_parallel=10 -> wall ~500ms
     (sequential would be 5000ms; 100x parallel would flood).
  2. NEGATIVE: peak in-flight <= max_parallel even with 100 tasks
     all submitted at once. Without the cap, 100 LLM calls in
     flight would breach any sane provider rate limit.
  3. NEGATIVE: results returned in SUBMISSION order, NOT completion.
     Staggered task durations should not reorder results.
  4. NEGATIVE: one task raising -> sibling tasks STILL complete;
     the failed task's slot has error set, result=None.
  5. NEGATIVE: per_task_timeout_s captures hung tasks; siblings
     unblocked.
  6. NEGATIVE: empty submission returns ([], stats with 0 submitted)
     immediately, no error, no worker_fn calls.
  7. NEGATIVE: max_parallel=1 forces sequential execution (proves
     the cap is actually enforced even at extreme).
  8. NEGATIVE: max_parallel=200 (more than 100 tasks) does NOT
     deadlock or over-fire; gracefully runs all in one cohort.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def _load_pool():
    p = REPO / "libs" / "py" / "documind_core" / "dispatch_pool.py"
    spec = importlib.util.spec_from_file_location("dispatch_pool", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dispatch_pool"] = mod
    spec.loader.exec_module(mod)
    return mod


pm = _load_pool()
DispatchPool = pm.DispatchPool


# Worker factory
def make_worker(*, per_task_s=0.05, raise_for=None, hang_for=None):
    raise_for = raise_for or set()
    hang_for = hang_for or set()

    async def worker(task):
        if task in raise_for:
            raise RuntimeError(f"task {task} simulated failure")
        if task in hang_for:
            await asyncio.sleep(60.0)  # will timeout
        await asyncio.sleep(per_task_s)
        return f"done:{task}"

    return worker


async def main():
    # Step 1: 100 tasks, max_parallel=10, bounded wall
    step("1. 100 tasks at 50ms each, max_parallel=10 -> wall ~500ms")
    pool = DispatchPool(worker_fn=make_worker(per_task_s=0.05), max_parallel=10)
    tasks = [f"t{i}" for i in range(100)]
    t0 = time.monotonic()
    results, stats = await pool.dispatch_all(tasks)
    elapsed = time.monotonic() - t0
    if elapsed > 1.5:
        fail(f"100 tasks at 50ms with max_parallel=10 took {elapsed:.2f}s (target <1.5s)")
    if len(results) != 100:
        fail(f"expected 100 results, got {len(results)}")
    if stats.completed != 100:
        fail(f"expected all 100 completed, got {stats.completed}")
    ok(f"100 tasks done in {elapsed * 1000:.0f}ms; peak in-flight={stats.peak_in_flight}")

    # Step 2: peak in-flight bounded
    step("2. NEGATIVE: peak in-flight <= max_parallel even with 100 tasks")
    if stats.peak_in_flight > 10:
        fail(
            f"semaphore breached: peak={stats.peak_in_flight} > max_parallel=10. "
            f"100 LLM calls in flight would breach provider rate limits."
        )
    if stats.peak_in_flight < 5:
        fail(
            f"suspiciously low peak={stats.peak_in_flight} - tasks may not "
            f"actually have run in parallel"
        )
    ok(f"peak in-flight = {stats.peak_in_flight} (cap was 10)")

    # Step 3: submission order preserved
    step("3. NEGATIVE: results in submission order, NOT completion order")
    # Staggered durations - task N takes (N % 5) * 10 ms
    async def staggered_worker(task):
        idx = int(task[1:])
        await asyncio.sleep((idx % 5) * 0.01)
        return f"done:{task}"

    pool = DispatchPool(worker_fn=staggered_worker, max_parallel=20)
    tasks = [f"t{i}" for i in range(20)]
    results, _ = await pool.dispatch_all(tasks)
    indices = [r.index for r in results]
    if indices != list(range(20)):
        fail(f"results not in submission order: {indices}")
    task_names = [r.task for r in results]
    if task_names != tasks:
        fail(f"task order drift: {task_names}")
    ok(f"submission order preserved across staggered completions")

    # Step 4: error isolation
    step("4. NEGATIVE: one task raising -> siblings complete cleanly")
    pool = DispatchPool(
        worker_fn=make_worker(per_task_s=0.01, raise_for={"t5", "t12"}),
        max_parallel=10,
    )
    tasks = [f"t{i}" for i in range(20)]
    results, stats = await pool.dispatch_all(tasks)
    if stats.failed != 2:
        fail(f"expected 2 failed tasks, got {stats.failed}")
    if stats.completed != 18:
        fail(f"expected 18 completed, got {stats.completed}")
    failed_set = set(stats.failed_indices)
    if failed_set != {5, 12}:
        fail(f"wrong failed indices: {failed_set}")
    # Verify each failed slot has error set, result=None
    for r in results:
        if r.task in {"t5", "t12"}:
            if r.error is None or "simulated failure" not in r.error:
                fail(f"task {r.task} error not captured: {r.error!r}")
            if r.result is not None:
                fail(f"task {r.task} should have result=None on error")
        else:
            if r.error is not None:
                fail(f"sibling task {r.task} got error: {r.error}")
            if r.result != f"done:{r.task}":
                fail(f"sibling task {r.task} bad result: {r.result}")
    ok(f"2 failed isolated; 18 siblings completed; failed_indices={sorted(failed_set)}")

    # Step 5: per-task timeout
    step("5. NEGATIVE: per_task_timeout captures hung tasks")
    pool = DispatchPool(
        worker_fn=make_worker(per_task_s=0.01, hang_for={"t3"}),
        max_parallel=10,
        per_task_timeout_s=0.5,
    )
    tasks = [f"t{i}" for i in range(10)]
    t0 = time.monotonic()
    results, stats = await pool.dispatch_all(tasks)
    elapsed = time.monotonic() - t0
    if elapsed > 1.0:
        fail(f"hung task blocked the cohort: wall={elapsed:.2f}s")
    if 3 not in stats.failed_indices:
        fail(f"hung task t3 should be in failed_indices: {stats.failed_indices}")
    t3_result = results[3]
    if t3_result.error is None or "Timeout" not in t3_result.error:
        fail(f"t3 should have TimeoutError: {t3_result.error!r}")
    ok(f"hung task captured at {elapsed * 1000:.0f}ms; siblings unblocked")

    # Step 6: empty submission
    step("6. NEGATIVE: empty submission returns immediately")
    called = [0]
    async def counting_worker(task):
        called[0] += 1
        return task

    pool = DispatchPool(worker_fn=counting_worker, max_parallel=10)
    results, stats = await pool.dispatch_all([])
    if results:
        fail(f"empty submission should return [], got {results}")
    if stats.submitted != 0:
        fail(f"stats.submitted should be 0, got {stats.submitted}")
    if called[0] != 0:
        fail(f"worker_fn called on empty submission: {called[0]}")
    ok("empty submission returns cleanly without worker_fn call")

    # Step 7: max_parallel=1 sequential
    step("7. NEGATIVE: max_parallel=1 forces strict sequential execution")
    pool = DispatchPool(worker_fn=make_worker(per_task_s=0.05), max_parallel=1)
    tasks = [f"t{i}" for i in range(5)]
    t0 = time.monotonic()
    results, stats = await pool.dispatch_all(tasks)
    elapsed = time.monotonic() - t0
    # Sequential: 5 * 50ms = 250ms minimum
    if elapsed < 0.20:
        fail(
            f"max_parallel=1 should force sequential (>= 0.25s), got {elapsed:.2f}s. "
            f"Cap not enforced - 5 tasks ran in parallel"
        )
    if stats.peak_in_flight != 1:
        fail(f"max_parallel=1 should give peak=1, got {stats.peak_in_flight}")
    ok(f"sequential enforced: 5 tasks in {elapsed * 1000:.0f}ms; peak=1")

    # Step 8: max_parallel >> tasks
    step("8. NEGATIVE: max_parallel=200 with 50 tasks - no deadlock, no over-fire")
    pool = DispatchPool(worker_fn=make_worker(per_task_s=0.02), max_parallel=200)
    tasks = [f"t{i}" for i in range(50)]
    t0 = time.monotonic()
    results, stats = await pool.dispatch_all(tasks)
    elapsed = time.monotonic() - t0
    if elapsed > 0.3:
        fail(f"50 tasks with max_parallel=200 took {elapsed * 1000:.0f}ms (target <300ms)")
    # Peak should be ~50 (all running at once, capped by task count not max_parallel)
    if stats.peak_in_flight > 50:
        fail(f"peak={stats.peak_in_flight} exceeds task count 50 (over-fire)")
    if stats.peak_in_flight < 30:
        fail(f"peak={stats.peak_in_flight} suspiciously low - parallelism not working")
    if stats.completed != 50:
        fail(f"expected 50 completed, got {stats.completed}")
    ok(f"50 tasks in {elapsed * 1000:.0f}ms; peak={stats.peak_in_flight} (no deadlock)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 DISPATCH-POOL STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
