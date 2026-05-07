#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for B3 — Lobster-style review-loop cap (Phase B3).

Verifies the route_after_review function in app/langgraph_flow.py:

  - low confidence + retry_count < MAX_REVIEW_ITERATIONS → 'review_retry_bump'
  - retry_count >= MAX_REVIEW_ITERATIONS → exits loop (advisory_board or policy)
  - high confidence → never loops, regardless of retry_count

Negative assertions (the locks):
  1. The 4th iteration (retry_count=3) MUST NOT route to review_retry_bump
     — that's the cap. A bug here = infinite loop = pipeline runaway.
  2. high-confidence + retry_count=2 → must NOT pre-emptively retry just
     because retries are still allowed.
  3. The graph MUST contain an edge from review_retry_bump → worker_execute
     — without this the bump node is a dead end and tasks hang.

Resource tag = readonly (source-level + module-level checks; no DB).

Why this drill: B3 is the cheap quality win. Without the cap drill, a
future regression like 'lower threshold + remove cap' would silently
ship and burn unbounded local Ollama tokens (or unbounded cloud cost
once the routed path is wired by B1).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
FLOW_FILE = SVC / "app" / "langgraph_flow.py"


def _bootstrap_flow_module() -> ModuleType:
    """Load langgraph_flow.py with stubs for its imports.

    The module imports 'agents' (which pulls in mcp + httpx) — too heavy
    for a readonly drill. We only need the constants + route_after_review
    function to test routing logic.
    """
    pkg_name = "b3_app"
    if pkg_name not in sys.modules:
        sys.modules[pkg_name] = ModuleType(pkg_name)
        sys.modules[pkg_name].__path__ = [str(SVC / "app")]

    # Stub agents module: route_after_review is a closure inside build_graph
    # so we can't easily call it without the full closure. Instead we
    # source-grep langgraph_flow.py for the constants + the routing rules.
    return None  # noqa: returns nothing — drill works via source inspection


def main() -> int:
    text = FLOW_FILE.read_text(encoding="utf-8")

    print("-- 1. POSITIVE: B3 constants are present --")
    assert "MAX_REVIEW_ITERATIONS = 3" in text, "MAX_REVIEW_ITERATIONS constant missing"
    assert "REVIEW_THRESHOLD = 0.7" in text, "REVIEW_THRESHOLD constant missing"
    print("  ok: MAX_REVIEW_ITERATIONS=3, REVIEW_THRESHOLD=0.7")

    print("-- 2. POSITIVE: route_after_review checks both confidence AND cap --")
    # The function body must reference both constants.
    after_review_idx = text.find("def route_after_review")
    assert after_review_idx >= 0, "route_after_review function missing"
    after_review_body = text[after_review_idx:after_review_idx + 800]
    assert "REVIEW_THRESHOLD" in after_review_body, (
        "route_after_review must reference REVIEW_THRESHOLD"
    )
    assert "MAX_REVIEW_ITERATIONS" in after_review_body, (
        "route_after_review must reference MAX_REVIEW_ITERATIONS"
    )
    assert "review_retry_bump" in after_review_body, (
        "route_after_review must dispatch to 'review_retry_bump'"
    )
    print("  ok: route checks both threshold AND iteration cap")

    print("-- 3. POSITIVE: review_retry_bump node defined --")
    assert "async def review_retry_bump" in text, "review_retry_bump node not declared"
    bump_idx = text.find("async def review_retry_bump")
    bump_body = text[bump_idx:bump_idx + 1000]
    assert "retry_count" in bump_body, "review_retry_bump must update retry_count"
    assert 'event": "review_retry"' in bump_body or '"event": "review_retry"' in bump_body, (
        "review_retry_bump must emit audit event"
    )
    print("  ok: review_retry_bump node declared and audits the loop")

    print("-- 4. POSITIVE: graph wires review_retry_bump → worker_execute --")
    # Without this edge, the bump node is a dead end → graph hangs.
    assert 'add_edge("review_retry_bump", "worker_execute")' in text, (
        "review_retry_bump → worker_execute edge missing — bump becomes dead end"
    )
    print("  ok: bump node routes back to worker_execute (loop closes)")

    print("-- 5. POSITIVE: graph registers review_retry_bump as a node --")
    assert 'add_node("review_retry_bump"' in text, (
        "review_retry_bump not added to graph"
    )
    print("  ok: review_retry_bump in graph nodes")

    print("-- 6. POSITIVE: conditional edge from review_output includes the new branch --")
    # Find the add_conditional_edges block for review_output. Use the
    # route_after_review function name as anchor — appears exactly once.
    anchor = "route_after_review,"
    cond_idx = text.find(anchor)
    assert cond_idx >= 0, "add_conditional_edges with route_after_review missing"
    # Look at the dispatch dict that follows — closing brace marks end.
    cond_block = text[cond_idx:cond_idx + 600]
    end = cond_block.find("},")
    if end >= 0:
        cond_block = cond_block[:end + 2]
    assert "review_retry_bump" in cond_block, (
        f"review_output's conditional edge dict must include 'review_retry_bump'. "
        f"Block: {cond_block[:300]!r}"
    )
    print("  ok: review_output dispatch includes retry branch")

    print("-- 7. NEGATIVE: low conf + retry=3 must NOT loop (cap honored) --")
    # We can't easily call the closure-bound function, so inspect the
    # condition source: it MUST use '<' (strictly less than), not '<='
    # for the iteration cap. Otherwise retry=3 would still loop.
    rule_idx = after_review_body.find("retry_count <")
    assert rule_idx >= 0, "missing retry_count comparison"
    # Pick out the substring around the comparison.
    rule_snip = after_review_body[rule_idx:rule_idx + 60]
    assert "retry_count < MAX_REVIEW_ITERATIONS" in rule_snip, (
        f"cap comparison must use '<' (strict). Found: {rule_snip!r}"
    )
    print("  ok: cap uses '<' (strict) — retry=3 exits loop")

    print("-- 8. NEGATIVE: high confidence MUST NOT retry --")
    # The condition must require BOTH conditions (low conf AND retry < cap).
    # Look for 'and' between them.
    cond_substr = after_review_body[
        after_review_body.find("confidence < REVIEW_THRESHOLD"):
        after_review_body.find("confidence < REVIEW_THRESHOLD") + 120
    ]
    assert " and " in cond_substr, (
        "confidence + cap must be AND-joined; if OR-joined, high-conf "
        "tasks would still loop on retry_count<3"
    )
    print("  ok: condition is AND-joined (high conf never retries)")

    print("-- 9. POSITIVE: TaskView has retry_count field --")
    models_text = (SVC / "app" / "models.py").read_text(encoding="utf-8")
    assert "retry_count: int = 0" in models_text, (
        "TaskView.retry_count field missing"
    )
    print("  ok: TaskView.retry_count present with default 0")

    print("-- 10. POSITIVE: AgenticState declares retry_count --")
    assert "retry_count: int" in text, "AgenticState.retry_count missing"
    print("  ok: AgenticState carries retry_count through the graph")

    print()
    print("ALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
