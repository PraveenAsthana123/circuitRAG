#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: multi_hop_agent parallel sub-question fanout (Phase 3A).

Locks the contract that:

  fanout_retrieval(sub_questions, retriever, loop_cb, ...)
    -> N retrievals issued in parallel, bounded by max_parallel
    -> per-hop timeout enforced via asyncio.wait_for
    -> total_timeout enforced on the cohort
    -> trace + gathered_context preserve INPUT order, not completion
    -> per-hop error isolation: one raise doesn't sink siblings
    -> loop_cb.record_step still called per-result for tool budget
       and repeated-result-hash loop detection

Eight steps. Six negative assertions.

  1. Parallel: 4 sub-questions at 100ms each finish in <200ms wall.
  2. Trace + gathered_context preserve INPUT order regardless of
     completion order.
  3. NEGATIVE: max_parallel=2 caps in-flight count to 2.
  4. NEGATIVE: one hop raising does NOT sink the cohort.
  5. NEGATIVE: per-hop timeout captured in trace; siblings unblocked.
  6. NEGATIVE: max_hops caps the cohort even if planner returns more.
  7. NEGATIVE: loop detection breaks the result-walk.
  8. NEGATIVE: empty sub_questions returns immediately, no error.

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


def _load_fanout():
    p = REPO / "services" / "inference-svc" / "app" / "agents" / "multi_hop_fanout.py"
    spec = importlib.util.spec_from_file_location("multi_hop_fanout", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["multi_hop_fanout"] = mod
    spec.loader.exec_module(mod)
    return mod


fan = _load_fanout()
fanout_retrieval = fan.fanout_retrieval


class _StubRetriever:
    def __init__(self, *, per_hop_s=0.0, chunks_for=None, raise_for=None):
        self.calls = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self._per_hop_s = per_hop_s
        self._chunks_for = chunks_for or {}
        self._raise_for = raise_for or {}

    async def retrieve(self, *, tenant_id, correlation_id, query,
                       top_k=3, strategy="hybrid"):
        self.calls.append(query)
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            if query in self._raise_for:
                raise self._raise_for[query]
            await asyncio.sleep(self._per_hop_s)
            return self._chunks_for.get(query, [
                {"chunk_id": f"chunk_for_{query}", "text": f"text for {query}"},
            ])
        finally:
            self.in_flight -= 1


_NONE = object()


class _StubBreaker:
    def __init__(self, *, stop_after=None, stop_value="loop-detected"):
        self.steps = []
        self._stop_after = stop_after
        self._stop_value = stop_value

    def record_step(self, *, action, result_hash):
        self.steps.append((action, result_hash))
        if self._stop_after is not None and len(self.steps) > self._stop_after:
            return self._stop_value
        return _NONE


async def main():
    # Step 1
    step("1. 4 hops at 100ms each finish in <200ms wall (parallel)")
    retr = _StubRetriever(per_hop_s=0.1)
    cb = _StubBreaker()
    sub_qs = [f"q{i}" for i in range(4)]
    t0 = time.monotonic()
    trace, gathered, stop = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=10,
    )
    elapsed = time.monotonic() - t0
    if elapsed > 0.25:
        fail(f"sequential? 4 x 100ms took {elapsed * 1000:.0f}ms (target < 200ms)")
    if len(trace) != 4 or len(gathered) != 4:
        fail(f"expected 4 trace + 4 gathered, got {len(trace)} + {len(gathered)}")
    if stop is not _NONE:
        fail(f"stop should be sentinel, got {stop!r}")
    ok(f"4 hops parallel in {elapsed * 1000:.0f}ms")

    # Step 2
    step("2. trace + gathered preserve input order regardless of completion order")

    class _StaggeredRetriever(_StubRetriever):
        async def retrieve(self, *, query, **kw):
            self.calls.append(query)
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            try:
                idx = int(query[1:])
                await asyncio.sleep(0.2 - idx * 0.05)
                return [{"chunk_id": f"c_{query}", "text": f"text for {query}"}]
            finally:
                self.in_flight -= 1

    retr = _StaggeredRetriever()
    cb = _StubBreaker()
    sub_qs = ["q0", "q1", "q2", "q3"]
    trace, gathered, _ = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=10,
    )
    sub_qs_in_trace = [t["sub_q"] for t in trace]
    if sub_qs_in_trace != ["q0", "q1", "q2", "q3"]:
        fail(f"trace order drift: {sub_qs_in_trace}")
    if not gathered[0].startswith("Q: q0"):
        fail(f"gathered[0] should start with 'Q: q0', got {gathered[0][:30]!r}")
    if not gathered[3].startswith("Q: q3"):
        fail(f"gathered[3] should start with 'Q: q3', got {gathered[3][:30]!r}")
    ok(f"input order preserved despite staggered completion: {sub_qs_in_trace}")

    # Step 3
    step("3. NEGATIVE: max_parallel=2 caps in-flight count (6 hops)")
    retr = _StubRetriever(per_hop_s=0.05)
    cb = _StubBreaker()
    sub_qs = [f"q{i}" for i in range(6)]
    await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=2, max_hops=10,
    )
    if retr.peak_in_flight > 2:
        fail(f"semaphore breached: peak in-flight={retr.peak_in_flight}")
    ok(f"peak in-flight = {retr.peak_in_flight} (within max_parallel=2)")

    # Step 4
    step("4. NEGATIVE: one hop raising does NOT sink siblings")
    retr = _StubRetriever(
        per_hop_s=0.01,
        raise_for={"q1": RuntimeError("simulated failure")},
    )
    cb = _StubBreaker()
    sub_qs = ["q0", "q1", "q2"]
    trace, gathered, _ = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=10,
    )
    if len(trace) != 3:
        fail(f"expected 3 trace entries, got {len(trace)}")
    error_entries = [t for t in trace if t.get("error")]
    if len(error_entries) != 1:
        fail(f"expected 1 error entry, got {len(error_entries)}")
    if error_entries[0]["sub_q"] != "q1":
        fail(f"wrong sub_q errored: {error_entries[0]}")
    if "simulated failure" not in error_entries[0]["error"]:
        fail(f"error message lost: {error_entries[0]['error']!r}")
    if len(gathered) != 2:
        fail(f"expected 2 successful gathered, got {len(gathered)}")
    if "Q: q1" in "\n".join(gathered):
        fail("errored hop leaked into gathered_context")
    ok(f"q1 errored cleanly; q0 + q2 surfaced; gathered count={len(gathered)}")

    # Step 5
    step("5. NEGATIVE: per-hop timeout captured in trace")

    class _SlowQ1Retriever(_StubRetriever):
        async def retrieve(self, *, query, **kw):
            self.calls.append(query)
            if query == "q1":
                await asyncio.sleep(2.0)
            else:
                await asyncio.sleep(0.01)
            return [{"chunk_id": f"c_{query}", "text": f"t {query}"}]

    retr = _SlowQ1Retriever()
    cb = _StubBreaker()
    sub_qs = ["q0", "q1", "q2"]
    t0 = time.monotonic()
    trace, gathered, _ = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=10,
        total_timeout_s=10.0,
        per_hop_timeout_s=0.2,
    )
    elapsed = time.monotonic() - t0
    if elapsed > 0.5:
        fail(f"cohort waited beyond per_hop_timeout: {elapsed * 1000:.0f}ms")
    error_entries = [t for t in trace if t.get("error")]
    if len(error_entries) != 1:
        fail(f"expected 1 timeout error entry, got {len(error_entries)}")
    if "Timeout" not in error_entries[0]["error"]:
        fail(f"timeout error not labelled: {error_entries[0]['error']!r}")
    ok(f"q1 timed out; cohort done in {elapsed * 1000:.0f}ms (siblings unblocked)")

    # Step 6
    step("6. NEGATIVE: max_hops=3 caps cohort even with 50 sub_questions")
    retr = _StubRetriever(per_hop_s=0.01)
    cb = _StubBreaker()
    sub_qs = [f"q{i}" for i in range(50)]
    trace, gathered, _ = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=3,
    )
    if len(retr.calls) != 3:
        fail(f"max_hops violated: {len(retr.calls)} retrieve calls")
    if len(trace) != 3 or len(gathered) != 3:
        fail(f"trace/gathered not capped: {len(trace)}/{len(gathered)}")
    ok(f"50 sub_questions capped to 3 retrieves")

    # Step 7
    step("7. NEGATIVE: loop_cb stop at hop-2 breaks the result walk")
    retr = _StubRetriever(per_hop_s=0.01)
    cb = _StubBreaker(stop_after=2, stop_value="loop_detected")
    sub_qs = ["q0", "q1", "q2", "q3"]
    trace, gathered, stop = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=sub_qs, loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=10,
    )
    if stop is _NONE:
        fail(f"stop sentinel returned when loop should have fired")
    if stop != "loop_detected":
        fail(f"unexpected stop value: {stop!r}")
    if len(gathered) != 2:
        fail(f"expected 2 gathered (q0+q1 before stop), got {len(gathered)}")
    if len(retr.calls) != 4:
        fail(f"all 4 hops should have fired in parallel; got {len(retr.calls)}")
    ok(f"loop detected; gathered={len(gathered)}; all 4 hops still ran")

    # Step 8
    step("8. NEGATIVE: empty sub_questions returns immediately, no error")
    retr = _StubRetriever()
    cb = _StubBreaker()
    trace, gathered, stop = await fanout_retrieval(
        retriever=retr, tenant_id="t", correlation_id="c",
        sub_questions=[], loop_cb=cb, stop_sentinel=_NONE,
        max_parallel=4, max_hops=10,
    )
    if trace or gathered:
        fail(f"empty sub_qs should return empty: {trace}, {gathered}")
    if stop is not _NONE:
        fail(f"empty sub_qs should return stop sentinel, got {stop!r}")
    if retr.calls:
        fail(f"empty sub_qs should NOT call retriever; got {retr.calls}")
    ok("empty sub_questions returns cleanly without retriever call")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 MULTI-HOP FANOUT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
