#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ElasticSearcher skeleton contract.

Locks services/retrieval-svc/app/services/elastic_searcher.py — the
PLANNED vectorless-retrieval wrapper. Without this drill, the
skeleton can silently lose its tenant-isolation contract or
graceful-degrade-on-missing-client behavior, both of which are
required invariants when the operator wires ES indexing later.

Negative assertions cover: file absent; missing tenant_id filter;
fail-loud on ImportError instead of degrade-to-empty; non-async
search; class doesn't take url + index args.
"""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ES_FILE = REPO / "services" / "retrieval-svc" / "app" / "services" / "elastic_searcher.py"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: elastic_searcher.py exists --")
    if not ES_FILE.exists():
        raise AssertionError(f"missing {ES_FILE.relative_to(REPO)}")
    text = ES_FILE.read_text(encoding="utf-8")
    print("  ok: elastic_searcher.py present")

    print("-- 2. POSITIVE: ElasticSearcher class with canonical constructor --")
    require(text, "class ElasticSearcher:", "ElasticSearcher class")
    require(text, "url: str", "url constructor arg")
    require(text, "index: str", "index constructor arg")
    print("  ok: class + url + index args")

    print("-- 3. POSITIVE: async search() takes tenant_id + query + top_k --")
    require(text, "async def search(", "async search method")
    require(text, "tenant_id: str", "tenant_id arg")
    require(text, "top_k: int", "top_k arg")
    require(text, "query: str", "query arg")
    print("  ok: async search signature")

    print("-- 4. NEGATIVE: search MUST filter by tenant_id (defense in depth) --")
    # Cross-tenant data leakage is the most-load-bearing security concern
    # for a multi-tenant retrieval surface. Drill enforces the term filter.
    require(text, '{"term": {"tenant_id": tenant_id}}', "tenant_id term filter")
    print("  ok: tenant_id term filter present in bool query")

    print("-- 5. NEGATIVE: search MUST degrade gracefully when ES client missing --")
    # Phase 1 dev doesn't install elasticsearch client. search() must
    # return [] not raise, so the rest of HybridRetriever continues.
    require(text, "except ImportError", "ImportError catch")
    require(text, "RuntimeError(\"elasticsearch client unavailable\")",
            "RuntimeError sentinel")
    require(text, "return []", "graceful empty fallback")
    print("  ok: graceful degrade on missing ES client")

    print("-- 6. NEGATIVE: search MUST degrade on ES query failures --")
    # If ES is up but the query fails (network, parse error, etc.),
    # don't crash the request. Return empty + log warning.
    require(text, "except Exception", "broad except for ES query failures")
    require(text, "elastic_search_failed", "structured log marker")
    print("  ok: graceful degrade on ES query failure")

    print("-- 7. POSITIVE: hit shape includes chunk_id + score + content --")
    require(text, '"chunk_id"', "chunk_id in hit")
    require(text, '"score"', "score in hit")
    require(text, '"content"', "content in hit")
    print("  ok: canonical hit shape")

    print("-- 8. POSITIVE: aclose() method for proper client cleanup --")
    require(text, "async def aclose(", "aclose method")
    require(text, "self._client = None", "client reset on close")
    print("  ok: aclose() resets client")

    print("-- 9. NEGATIVE: docstring MUST mark this as PLANNED status --")
    # Without the PLANNED marker, callers may assume Phase-1 retrieval
    # uses ES (it doesn't — only Qdrant + Neo4j). Honest framing prevents
    # speculative integration that isn't actually wired.
    require(text, "PLANNED feature surface", "PLANNED status declaration")
    require(text, "Phase 1", "Phase-1 framing")
    print("  ok: status honestly marked PLANNED")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
