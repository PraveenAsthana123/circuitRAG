#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: retrieval-svc min_score similarity floor (compression-tools-audit follow-up).

Per CLAUDE.md §39 + §43 + docs/architecture/compression-tools-audit-2026-05-04.md
+ docs/architecture/rag-deep-test-2026-05-04.md. Locks the empirical-gap fix
that closes:

  Q: "What is Half-Life 2 known for?" against a corpus with NO Half-Life
     content. WAS: 5 chunks returned (mobile phones, ink, Google).
     NOW: caller passes min_score=0.3 → 0 chunks returned (correctly).

Contract:
  - RetrieveRequest.min_score field exists with bounds [0.0, 1.0]
  - Default min_score=0.0 preserves legacy unfiltered behavior
  - HybridRetriever.retrieve filters chunks where score < min_score
  - Filter runs AFTER fused top_k, so min_score never breaks ranking
  - Filter applies only when min_score > 0.0 (skip when 0.0)
  - Drop count + kept count + threshold logged for observability

Eight steps. Six negative.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "services" / "retrieval-svc" / "app" / "schemas" / "__init__.py"
RETRIEVER = REPO / "services" / "retrieval-svc" / "app" / "services" / "hybrid_retriever.py"


def main() -> int:
    print("-- 1. POSITIVE: schema + retriever files exist --")
    if not SCHEMA.exists() or not RETRIEVER.exists():
        print("x missing schema or retriever file")
        return 1
    schema_src = SCHEMA.read_text(encoding="utf-8")
    retriever_src = RETRIEVER.read_text(encoding="utf-8")
    print("  ok: both source files present")

    print("-- 2. POSITIVE: RetrieveRequest declares min_score field --")
    if "min_score:" not in schema_src:
        print("x min_score field missing from RetrieveRequest")
        return 1
    if "min_score: float" not in schema_src:
        print("x min_score must be typed float")
        return 1
    print("  ok: min_score: float declared")

    print("-- 3. NEGATIVE: min_score has bounds [0.0, 1.0] (no negative or >1) --")
    # Pydantic Field(ge=0.0, le=1.0) lock
    if "ge=0.0" not in schema_src or "le=1.0" not in schema_src:
        print("x min_score must enforce ge=0.0, le=1.0")
        return 1
    print("  ok: bounds enforced [0.0, 1.0]")

    print("-- 4. NEGATIVE: min_score default is 0.0 (legacy-compat) --")
    # Caller-opt-in. Default 0.0 means existing callers see no behavior change.
    if "default=0.0" not in schema_src:
        print("x min_score default must be 0.0 to preserve legacy callers")
        return 1
    print("  ok: default=0.0 (legacy callers unaffected)")

    print("-- 5. NEGATIVE: filter is skipped when threshold == 0.0 --")
    # Skipping when 0.0 is the no-op path. Drilled to lock the optimization
    # so a future contributor doesn't accidentally apply the filter even
    # at threshold 0.0 (which would still drop chunks scored exactly 0,
    # which CAN happen on cold-start/no-embedding cases).
    # Post-2741a93: the threshold may be EITHER request.min_score (legacy)
    # OR effective_min_score (when best_config_loader Stage-2 wire is
    # active and the caller didn't explicitly set min_score). Either form
    # correctly skips the filter at 0.0.
    has_legacy = "request.min_score > 0.0" in retriever_src
    has_effective = "effective_min_score > 0.0" in retriever_src
    if not (has_legacy or has_effective):
        print("x retriever must guard the filter with `if (request.min_score|effective_min_score) > 0.0`")
        return 1
    print("  ok: filter guarded behind > 0.0")

    print("-- 6. NEGATIVE: filter applies AFTER top_k truncation --")
    # The min_score filter must run AFTER the fused top_k slice. Otherwise
    # the filter could drop chunks BEFORE ranking, breaking the contract
    # that callers asking for top_k=5 get the best 5 (subject to floor).
    truncate_idx = retriever_src.find("fused = fused[: request.top_k]")
    filter_idx = retriever_src.find("if effective_min_score > 0.0:")
    if filter_idx < 0:
        # Fall back to legacy form
        filter_idx = retriever_src.find("if request.min_score > 0.0:")
    if truncate_idx < 0 or filter_idx < 0:
        print("x missing top_k truncation or min_score filter block")
        return 1
    if filter_idx < truncate_idx:
        print("x min_score filter must run AFTER top_k truncation; "
              "currently it runs before — that breaks ranking semantics")
        return 1
    print("  ok: filter is post-truncation (preserves top_k ranking)")

    print("-- 7. NEGATIVE: filter logs drop_count + kept_count + threshold --")
    # Observability lock: operator needs to see how aggressive the floor is
    # in production traffic. Without these counters, you can't tune the
    # floor based on real data.
    if 'min_score_filter' not in retriever_src:
        print("x retriever must emit a 'min_score_filter' log line")
        return 1
    if 'dropped=' not in retriever_src or 'kept=' not in retriever_src:
        print("x log line must include dropped + kept counters")
        return 1
    if 'threshold=' not in retriever_src:
        print("x log line must include the threshold value used")
        return 1
    print("  ok: observability lock — drop/kept/threshold all logged")

    print("-- 8. POSITIVE: source documents the empirical-test rationale --")
    # The why-this-exists is non-obvious. Future contributors should see
    # the link to the empirical RAG test that surfaced the gap, so they
    # don't second-guess the filter as cargo-cult.
    if "rag-deep-test-2026-05-04" not in schema_src:
        print("x schema source must reference the empirical test that "
              "surfaced this gap")
        return 1
    if "rag-deep-test-2026-05-04" not in retriever_src:
        print("x retriever source must reference the empirical test")
        return 1
    print("  ok: rationale documented in both source files")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
