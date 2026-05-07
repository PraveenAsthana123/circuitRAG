# RESOURCES: none
"""
Drill: HybridRetriever's transport-level breakers around vector and
graph backends fast-reject after N consecutive failures.

The catalog gap (circuit-breaker-gap-review.md item #1): the
RetrievalCircuitBreaker only watches RESULT QUALITY; the actual
Qdrant/Neo4j transport had no breaker. A 30-minute Qdrant outage
would have cost every retrieval the full timeout (~5s) instead of
a fast CircuitOpenError after the threshold.

Each step has a negative assertion §43-style:
 1. Healthy backends — both breakers stay CLOSED, response is not
    degraded. NEGATIVE: breakers must NOT trip on success.
 2. Vector backend raises N=3 in a row → vector_breaker OPENs;
    graph_breaker stays CLOSED. NEGATIVE: an unrelated namespace's
    breaker must not be affected.
 3. Once vector_breaker is OPEN, the next call FAST-REJECTS without
    invoking the vector backend. NEGATIVE: the failing backend
    must NOT be called when its CB is open.
 4. Independence — graph backend continues to be called even when
    vector_breaker is OPEN; response degraded=True (vector blocked,
    graph succeeded).
 5. Recovery — after recovery_timeout elapses, the next call
    transitions OPEN → HALF_OPEN. A successful backend response
    closes the breaker.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_retrieval_transport_breaker.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "retrieval-svc"))

from app.schemas import RetrieveRequest  # type: ignore  # noqa: E402
from app.services.hybrid_retriever import HybridRetriever  # type: ignore  # noqa: E402
from app.services.reranker import ReciprocalRankFusion  # type: ignore  # noqa: E402
from documind_core.circuit_breaker import CircuitBreaker, State  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# Stubs — same shape as drill_retrieval_degraded_envelope.
class _StubEmbedder:
    async def embed_query(self, q: str) -> list[float]:
        return [0.1] * 8


class _CountingVector:
    """Returns one chunk on success; raises when ``raise_n`` > 0
    (decremented per call). Tracks call count so step 3 can prove
    the breaker prevented a call."""

    def __init__(self, *, raise_n: int = 0) -> None:
        self.raise_n = raise_n
        self.call_count = 0

    async def search(self, *, tenant_id: str, query_vector, top_k: int) -> list[dict]:
        self.call_count += 1
        if self.raise_n > 0:
            self.raise_n -= 1
            raise ConnectionError("vector backend simulated transport failure")
        return [{
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": "from vector",
            "score": 0.9,
            "source": "vector",
            "page_number": 1,
        }]


class _CountingGraph:
    def __init__(self, *, raise_always: bool = False) -> None:
        self.raise_always = raise_always
        self.call_count = 0

    async def search(self, *, tenant_id: str, query: str, top_k: int) -> list[dict]:
        self.call_count += 1
        if self.raise_always:
            raise ConnectionError("graph backend simulated transport failure")
        return [{
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": "from graph",
            "score": 0.7,
            "source": "graph",
            "page_number": 1,
        }]


class _InMemoryCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get_json(self, key: str) -> Any | None:
        return self.store.get(key)

    async def set_json(self, key: str, value: Any, *, ttl: int = 0) -> None:
        self.store[key] = value


def _make_retriever(
    *, vector_raise_n: int = 0, graph_raise: bool = False,
    vector_breaker_recovery: float = 30.0,
):
    vec = _CountingVector(raise_n=vector_raise_n)
    grp = _CountingGraph(raise_always=graph_raise)
    vector_breaker = CircuitBreaker(
        "retrieval-vector-transport-test",
        failure_threshold=3,
        recovery_timeout=vector_breaker_recovery,
    )
    graph_breaker = CircuitBreaker(
        "retrieval-graph-transport-test",
        failure_threshold=3,
        recovery_timeout=30.0,
    )
    return (
        HybridRetriever(
            embedder=_StubEmbedder(),
            vector=vec,
            graph=grp,
            reranker=ReciprocalRankFusion(),
            cache=_InMemoryCache(),
            vector_breaker=vector_breaker,
            graph_breaker=graph_breaker,
        ),
        vec,
        grp,
        vector_breaker,
        graph_breaker,
    )


async def main() -> None:
    TENANT = str(uuid.uuid4())
    REQ = RetrieveRequest(query="anything", top_k=5, strategy="hybrid")

    step("1. Healthy backends — both breakers stay CLOSED, response not degraded")
    r, vec, grp, vbr, gbr = _make_retriever()
    resp = await r.retrieve(tenant_id=TENANT, request=REQ)
    if vbr.state is not State.CLOSED:
        fail(f"vector_breaker should be CLOSED, got {vbr.state}")
    if gbr.state is not State.CLOSED:
        fail(f"graph_breaker should be CLOSED, got {gbr.state}")
    if resp.degraded:
        fail("degraded=True on healthy path")
    ok(f"both breakers CLOSED; degraded=False; vec calls={vec.call_count} grp calls={grp.call_count}")

    step("2. Vector backend raises 3× → vector_breaker OPENs; graph stays CLOSED")
    r, vec, grp, vbr, gbr = _make_retriever(vector_raise_n=999)  # always raises
    # Drive 3 retrievals to trip the vector breaker.
    for _i in range(3):
        await r.retrieve(tenant_id=TENANT, request=REQ)
    if vbr.state is not State.OPEN:
        fail(
            f"vector_breaker should be OPEN after 3 failures, got {vbr.state}; "
            f"vector backend was called {vec.call_count} time(s)"
        )
    if gbr.state is not State.CLOSED:
        fail(
            f"graph_breaker should still be CLOSED (graph backend healthy), "
            f"got {gbr.state}"
        )
    ok(
        f"vector_breaker={vbr.state.value} graph_breaker={gbr.state.value} "
        f"after {vec.call_count} vector calls (3 failures tripped it)"
    )

    step("3. Vector breaker OPEN → fast-reject without invoking the backend")
    # Reset call count to measure ONLY this step's invocations.
    pre_calls = vec.call_count
    await r.retrieve(tenant_id=TENANT, request=REQ)
    if vec.call_count != pre_calls:
        fail(
            f"vector backend was called {vec.call_count - pre_calls} time(s) "
            f"despite breaker OPEN — fast-reject is broken"
        )
    ok("breaker OPEN → vector backend NOT called (fast-reject works)")

    step("4. Graph backend keeps being called even with vector breaker OPEN")
    pre_grp = grp.call_count
    resp = await r.retrieve(tenant_id=TENANT, request=REQ)
    if grp.call_count <= pre_grp:
        fail(
            "graph backend was NOT called when vector breaker is OPEN — "
            "backend independence broken (one bad backend should not block "
            "the other)"
        )
    if not resp.degraded:
        fail(
            "degraded=False but vector backend was breaker-rejected — "
            "degraded envelope should reflect ANY backend failure"
        )
    ok(
        f"graph still called (count={grp.call_count}); response carries "
        f"degraded=True from breaker rejection"
    )

    step("5. Recovery — vector breaker transitions OPEN → CLOSED after timeout")
    # Build a fresh retriever with a tiny recovery_timeout so we don't sleep 30s.
    r, vec, grp, vbr, gbr = _make_retriever(
        vector_raise_n=3, vector_breaker_recovery=0.5,
    )
    for _ in range(3):
        await r.retrieve(tenant_id=TENANT, request=REQ)
    if vbr.state is not State.OPEN:
        fail(f"vector_breaker should be OPEN, got {vbr.state}")
    # vec.raise_n is now 0 — next call would succeed if invoked.
    await asyncio.sleep(0.6)  # past recovery_timeout
    pre_calls = vec.call_count
    resp = await r.retrieve(tenant_id=TENANT, request=REQ)
    if vec.call_count == pre_calls:
        fail(
            "vector backend was NOT called after recovery_timeout elapsed — "
            "breaker stuck OPEN"
        )
    if vbr.state is not State.CLOSED:
        fail(
            f"vector_breaker should be CLOSED after successful probe, "
            f"got {vbr.state}"
        )
    if resp.degraded:
        fail("response should NOT be degraded after breaker recovered")
    ok(
        f"breaker recovered: OPEN → HALF_OPEN → CLOSED after probe "
        f"(state={vbr.state.value})"
    )

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 TRANSPORT-BREAKER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
