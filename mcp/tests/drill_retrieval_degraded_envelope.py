# RESOURCES: none
"""
Drill: RetrieveResponse.degraded reflects backend-failure honestly.

The catalog gap (drill_retrieval_timeout_envelope) was that the
response shape had no flag telling the caller "one of the backends
I asked for failed; this is partial." Without it, downstream
consumers (agent path, RAG answer path) silently use partial
context as if it were complete — bad confidence, bad caching,
bad UX.

This commit adds ``degraded: bool = False`` to RetrieveResponse
and drives it from the same ``backend_failed`` flag the
hybrid_retriever already uses internally to skip caching. The
drill exercises the new flag with stubbed backends — fast, no
Qdrant/Neo4j/Ollama dependency.

Negative assertions §43-style:
 1. All backends healthy → degraded=False, chunks present, response
    cached. NEGATIVE: degraded must NOT be True on the happy path.
 2. Graph backend raises, vector succeeds → degraded=True, vector
    chunks still present. NEGATIVE: chunks must NOT be empty when
    one backend works.
 3. Both backends raise → degraded=True, chunks empty. NEGATIVE: a
    fully-failed retrieval must NOT silently return success.
 4. Degraded result is NOT cached — second identical call goes
    through the full path again (cached=False). NEGATIVE: poisoned
    cache must not lock the partial result in for cache_ttl.
 5. Healthy result IS cached — second call returns cached=True.
    Sanity that the caching itself works.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_retrieval_degraded_envelope.py
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

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# ---------------------------------------------------------------------------
# Stubs — match the duck-typed shape HybridRetriever expects.
# ---------------------------------------------------------------------------
class _StubEmbedder:
    async def embed_query(self, q: str) -> list[float]:
        return [0.1] * 8

    async def aclose(self) -> None:
        return None


class _StubVector:
    """Returns one fixed chunk on success; raises on failure."""

    def __init__(self, *, raise_exc: bool = False) -> None:
        self._raise = raise_exc

    async def search(self, *, tenant_id: str, query_vector, top_k: int) -> list[dict]:
        if self._raise:
            raise RuntimeError("vector backend simulated failure")
        return [{
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": "from vector",
            "score": 0.9,
            "source": "vector",
            "page_number": 1,
        }]


class _StubGraph:
    def __init__(self, *, raise_exc: bool = False) -> None:
        self._raise = raise_exc

    async def search(self, *, tenant_id: str, query: str, top_k: int) -> list[dict]:
        if self._raise:
            raise RuntimeError("graph backend simulated failure")
        return [{
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": "from graph",
            "score": 0.7,
            "source": "graph",
            "page_number": 1,
        }]


class _InMemoryCache:
    """Cache shape required by HybridRetriever: get_json + set_json."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get_json(self, key: str) -> Any | None:
        return self.store.get(key)

    async def set_json(self, key: str, value: Any, *, ttl: int = 0) -> None:
        self.store[key] = value


def _make_retriever(
    *, vector_raises: bool = False, graph_raises: bool = False,
    cache: _InMemoryCache | None = None,
) -> tuple[HybridRetriever, _InMemoryCache]:
    cache = cache or _InMemoryCache()
    return HybridRetriever(
        embedder=_StubEmbedder(),
        vector=_StubVector(raise_exc=vector_raises),
        graph=_StubGraph(raise_exc=graph_raises),
        reranker=ReciprocalRankFusion(),
        cache=cache,
    ), cache


async def main() -> None:
    TENANT = str(uuid.uuid4())
    REQ = RetrieveRequest(query="anything", top_k=5, strategy="hybrid")

    step("1. All backends healthy → degraded=False, chunks present, cached")
    r, cache = _make_retriever()
    resp = await r.retrieve(tenant_id=TENANT, request=REQ)
    if resp.degraded:
        fail(
            f"degraded=True on the happy path! Both backends returned "
            f"successfully but the response says degraded. chunks={len(resp.chunks)}"
        )
    if not resp.chunks:
        fail("happy path returned 0 chunks; stubs broken")
    if not cache.store:
        fail("happy path did not write to cache; cache invariant broken")
    ok(f"degraded=False; {len(resp.chunks)} chunks; cache populated")

    step("2. Graph raises, vector succeeds → degraded=True, vector chunks present")
    r, cache = _make_retriever(graph_raises=True)
    resp = await r.retrieve(tenant_id=TENANT, request=REQ)
    if not resp.degraded:
        fail(
            "degraded=False even though graph backend raised! "
            "Caller has no signal that the result is partial."
        )
    if not resp.chunks:
        fail(
            "no chunks returned when only graph failed; vector chunks should "
            "still come through"
        )
    if any(c.source != "vector" for c in resp.chunks):
        fail(f"got non-vector chunks despite graph failure: {[c.source for c in resp.chunks]}")
    ok(f"degraded=True; {len(resp.chunks)} vector chunks; graph failure isolated")

    step("3. Both backends raise → degraded=True, chunks empty (no silent success)")
    r, _ = _make_retriever(vector_raises=True, graph_raises=True)
    resp = await r.retrieve(tenant_id=TENANT, request=REQ)
    if not resp.degraded:
        fail(
            "degraded=False with BOTH backends failed — caller would treat "
            "as if retrieval succeeded with empty results."
        )
    if resp.chunks:
        fail(f"chunks returned when all backends failed: {len(resp.chunks)}")
    ok("degraded=True; chunks empty; no silent success")

    step("4. Degraded result is NOT cached (cache poison guard)")
    r, cache = _make_retriever(graph_raises=True)
    resp1 = await r.retrieve(tenant_id=TENANT, request=REQ)
    if not resp1.degraded:
        fail("step 4 setup: expected first call to be degraded")
    # Cache should be empty even though chunks were returned —
    # degraded results must not get cached for cache_ttl seconds.
    if cache.store:
        fail(
            f"cache populated on degraded result! Subsequent callers would "
            f"hit cached partial data for cache_ttl seconds. cache={list(cache.store)}"
        )
    # Second call should ALSO go through the full path (cached=False).
    resp2 = await r.retrieve(tenant_id=TENANT, request=REQ)
    if resp2.cached:
        fail(
            "second degraded call returned cached=True — partial result was "
            "served as cache hit, defeating the cache-skip invariant"
        )
    ok("cache empty after degraded result; second call also goes through full path")

    step("5. Healthy result IS cached (sanity for the cache plumbing)")
    r, cache = _make_retriever()
    resp1 = await r.retrieve(tenant_id=TENANT, request=REQ)
    if resp1.degraded or resp1.cached:
        fail(f"step 5 setup: first call should be fresh + healthy, got {resp1}")
    resp2 = await r.retrieve(tenant_id=TENANT, request=REQ)
    if not resp2.cached:
        fail("second healthy call did NOT return cached=True; cache plumbing broken")
    if resp2.degraded:
        fail("cached response carries degraded=True; cache wrote a degraded value")
    ok(f"cache hit on second call (cached=True, degraded=False); plumbing intact")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 RETRIEVAL-DEGRADED-ENVELOPE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
