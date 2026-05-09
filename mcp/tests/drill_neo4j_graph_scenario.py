#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Neo4j graph scenario uses authenticated write/read smoke.

Locks the graph_db scenario in scripts/scenario_batch_and_inference.py so
it proves the Cypher path, not just that Neo4j returns an unauthenticated
401. The scenario must create a tenant-scoped graph row, read it back,
and clean up temporary nodes.

NEGATIVE: an unauthenticated 401 must not be treated as a graph smoke pass.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "scripts" / "scenario_batch_and_inference.py"


def require(src: str, needle: str, label: str) -> None:
    if needle not in src:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: scenario runner exists + parses --")
    src = SCENARIO.read_text(encoding="utf-8")
    ast.parse(src)
    print("  ok: scenario runner exists and is Python-valid")

    print("-- 2. POSITIVE: graph_db scenario uses Neo4j auth --")
    require(src, "DOCUMIND_NEO4J_USER", "Neo4j user env")
    require(src, "DOCUMIND_NEO4J_PASSWORD", "Neo4j password env")
    require(src, "Authorization", "Basic auth header")
    require(src, "Basic", "Basic auth scheme")
    print("  ok: graph_db scenario authenticates to Neo4j")

    print("-- 3. POSITIVE: graph_db scenario writes and reads graph shape --")
    for needle, label in [
        ("MERGE (d:Document", "Document MERGE"),
        ("MERGE (ch:Chunk", "Chunk MERGE"),
        ("MERGE (ent:Entity", "Entity MERGE"),
        ("MERGE (ch)-[:MENTIONS]->(ent)", "MENTIONS relation"),
        ("MATCH (d:Document", "Document readback"),
        ("RETURN ch.id AS chunk_id", "chunk readback"),
    ]:
        require(src, needle, label)
    print("  ok: scenario writes + reads Document/Chunk/Entity relation")

    print("-- 4. NEGATIVE: graph_db must not pass on unauthenticated 401 --")
    if "code in (200, 401)" in src:
        raise AssertionError("graph_db still treats HTTP 401 as PASS")
    if "401 expected without auth" in src:
        raise AssertionError("graph_db still documents unauthenticated 401 as success")
    require(src, '"status": "PASS" if smoke_query_passed else "FAIL"', "strict pass condition")
    print("  ok: graph_db PASS requires authenticated smoke_query_passed")

    print("-- 5. NEGATIVE: graph_db scenario cleans up temporary nodes --")
    require(src, "DETACH DELETE n", "temporary tenant cleanup")
    require(src, "tenant_cleaned_up", "cleanup evidence field")
    require(src, "scenario-graph-", "temporary tenant prefix")
    print("  ok: graph_db cleanup is explicit and evidenced")

    print("\nALL 5 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
