"""Parallel sub-question fanout for the multi-hop RAG agent.

Extracted from MultiHopRagAgent.run() into a pure-async helper so:

  * The fanout can be drilled in isolation - no documind_core / app
    package imports needed in the test harness.
  * Future agents (corrective RAG, plan-then-retrieve) can reuse the
    same fanout primitive with their own retriever + breaker.

Pre-extraction the inner loop ran sub-questions sequentially:

    for sub_q in sub_questions:
        chunks = await self._retrieval.retrieve(query=sub_q, ...)
        ...

3 hops x ~200 ms each = ~600 ms wall. Parallel = ~200 ms - a 3x
reduction at the most-common N=3 case, ~Nx at higher N.

What's preserved from the sequential design:

  * Trace order matches input sub_questions order, NOT completion
    order. Reproducibility for audit trails.
  * gathered_context preserves input order - synthesizer sees
    context in the order the planner intended.
  * loop_cb.record_step still called per-result for tool-budget
    accounting + repeated-result-hash loop detection.
  * Per-hop error isolation: one retrieve raising doesn't sink
    the cohort; the trace records the error.

What changes from the sequential design:

  * loop_cb.check_before_step is called ONCE before the cohort
    (not per-step). Mid-cohort total-timeout is enforced via
    asyncio.wait_for on the gather, not per-hop check_before_step.
  * Per-step timeout becomes per-hop asyncio.wait_for so a hung
    retrieval can't block the cohort beyond per_hop_timeout_s.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Protocol

log = logging.getLogger(__name__)


class _RetrieverProto(Protocol):
    """Duck-typed retriever - anything with this signature works.

    Production: ``app.services.RetrievalClient``.
    Test:        a stub recording every (query) call for assertions.
    """

    async def retrieve(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        query: str,
        top_k: int = 3,
        strategy: str = "hybrid",
    ) -> list[dict[str, Any]]:  # pragma: no cover - Protocol
        ...


class _LoopCBProto(Protocol):
    """Duck-typed loop circuit breaker. Production:
    documind_core.breakers.AgentLoopCircuitBreaker."""

    def record_step(
        self, *, action: str, result_hash: str,
    ) -> Any:  # pragma: no cover - Protocol
        ...


async def fanout_retrieval(
    *,
    retriever: _RetrieverProto,
    tenant_id: str,
    correlation_id: str,
    sub_questions: list[str],
    loop_cb: _LoopCBProto,
    stop_sentinel: Any,
    max_parallel: int = 4,
    max_hops: int = 4,
    total_timeout_s: float = 60.0,
    per_hop_timeout_s: float = 30.0,
) -> tuple[list[dict[str, Any]], list[str], Any]:
    """Run all sub-question retrievals in parallel, bounded.

    Args:
        retriever: anything with ``async retrieve(query=..., ...)``.
        tenant_id, correlation_id: passed through to every retrieve
            call so trace context propagates.
        sub_questions: the planner's output. Capped to ``max_hops``
            before fanout - a planner that emits 50 sub-questions
            would otherwise blow the per-PR budget.
        loop_cb: circuit breaker. Only ``record_step`` is called
            after the cohort; total/per-step timeouts enforced via
            asyncio.wait_for (NOT loop_cb's internal timer).
        stop_sentinel: the "no stop" value that loop_cb.record_step
            returns when nothing is wrong (typically
            ``AgentStopReason.NONE``). Comparing identity rather
            than truthiness - the breaker may return falsy stop
            reasons for some states.
        max_parallel: cap on simultaneously in-flight retrievals.
            Default 4 - high enough to amortize latency, low enough
            not to flood the retrieval-svc's per-tenant rate limit.
        max_hops: caps the cohort size. Sub-questions beyond this
            are dropped before fanout.
        total_timeout_s: cohort wall-clock cap. If exceeded, the
            gather is cancelled and we return whatever the breaker
            considers a stop.
        per_hop_timeout_s: per-retrieve deadline. A hung retrieval
            is captured as an error in the trace; siblings keep
            running.

    Returns:
        ``(trace, gathered_context, final_stop_reason)``:
            trace: list of {step, sub_q, chunks, result_hash[, error]}
            gathered_context: list of "Q: ...\\nchunk text..." strings
                in input order. Excludes hops with errors AND hops
                after a loop-detection stop fired during result-walk.
            final_stop_reason: stop_sentinel if cohort completed
                cleanly; otherwise whatever loop_cb.record_step
                returned.
    """
    sub_questions = sub_questions[:max_hops]
    if not sub_questions:
        return [], [], stop_sentinel

    sem = asyncio.Semaphore(max_parallel)

    async def _one_hop(
        sub_q: str,
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        async with sem:
            try:
                chunks = await asyncio.wait_for(
                    retriever.retrieve(
                        tenant_id=tenant_id,
                        correlation_id=correlation_id,
                        query=sub_q,
                        top_k=3,
                        strategy="hybrid",
                    ),
                    timeout=per_hop_timeout_s,
                )
                return sub_q, chunks, None
            except TimeoutError:
                log.warning(
                    "multi_hop_fanout_per_hop_timeout sub_q=%r timeout=%.1fs",
                    sub_q[:120], per_hop_timeout_s,
                )
                return sub_q, [], (
                    f"TimeoutError: per-hop > {per_hop_timeout_s:.1f}s"
                )
            except Exception as exc:  # noqa: BLE001 - error contained
                log.warning(
                    "multi_hop_fanout_hop_error sub_q=%r err=%s",
                    sub_q[:120], exc,
                )
                return sub_q, [], f"{type(exc).__name__}: {exc}"

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_one_hop(q) for q in sub_questions]),
            timeout=total_timeout_s,
        )
    except TimeoutError:
        log.error(
            "multi_hop_fanout_cohort_timeout total=%.1fs sub_qs=%d",
            total_timeout_s, len(sub_questions),
        )
        # Cohort timeout - return empty trace + a non-NONE stop.
        # The caller's ``check_before_step`` after this returns will
        # also see the breaker exhausted and skip the synthesizer.
        return [], [], "cohort_timeout"

    # Walk in input order: trace + gathered_context
    trace: list[dict[str, Any]] = []
    gathered: list[str] = []
    final_stop: Any = stop_sentinel

    for sub_q, chunks, err in results:
        if err is not None:
            trace.append({
                "step": "retrieve",
                "sub_q": sub_q,
                "chunks": 0,
                "result_hash": "",
                "error": err,
            })
            continue

        result_hash = hashlib.sha256(
            "".join(c.get("chunk_id", "") for c in chunks).encode()
        ).hexdigest()[:12]

        trace.append({
            "step": "retrieve",
            "sub_q": sub_q,
            "chunks": len(chunks),
            "result_hash": result_hash,
        })

        # Tool-budget + repeated-result-hash loop detection still
        # enforced here, walked in INPUT order so the breaker's
        # internal hash window sees the same sequence the
        # sequential code would have.
        step_stop = loop_cb.record_step(
            action="retrieve", result_hash=result_hash,
        )
        if step_stop is not stop_sentinel:
            log.info(
                "multi_hop_fanout_stop_during_walk reason=%s sub_q=%r",
                step_stop, sub_q[:60],
            )
            final_stop = step_stop
            break

        gathered.append(
            f"Q: {sub_q}\n"
            + "\n".join(c.get("text", "") for c in chunks)
        )

    return trace, gathered, final_stop
