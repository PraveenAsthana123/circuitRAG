# RESOURCES: readonly
"""
Drill: Council Phases 3-5 — Q1/Q2/Q3 picks locked.

Q1 trimmed_mean: drop highest+lowest, mean rest. NEGATIVE: 1.0 outlier
   does NOT pull aggregate up (proves trimming actually fires).
Q2 evidence demote: uncited claim → demote in [0, 0.5]. NEGATIVE: empty
   text → 'pass' (no false positives).
Q3 dissent: 2 divergent agents trigger has_dissent=True. NEGATIVE: all
   agents agreeing → has_dissent=False even with N=4.

These are pure functions — no Ollama needed for this drill.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from council_engine.agents.roles import AgentResponse  # noqa: E402
from council_engine.rounds import (  # noqa: E402
    EVIDENCE_DEMOTE_MAX,
    aggregate_confidence,
    check_evidence,
    detect_dissent,
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t): print(f"\n{BOLD}── {t} ──{NC}")
def ok(m): print(f"  {GREEN}✓ {m}{NC}")
def fail(m):
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ============================================================
    # Q1: Confidence aggregation
    # ============================================================
    step("1. trimmed_mean: 5 scores → drop high+low, mean rest")
    out = aggregate_confidence([0.1, 0.5, 0.6, 0.7, 0.95], mode="trimmed_mean")
    expected = (0.5 + 0.6 + 0.7) / 3
    if abs(out - expected) > 0.001:
        fail(f"trimmed_mean: expected {expected}, got {out}")
    ok(f"trimmed_mean = {out:.3f} (dropped 0.1 + 0.95)")

    step("2. NEGATIVE — single 1.0 outlier does NOT inflate trimmed_mean")
    out_with = aggregate_confidence([0.5, 0.5, 0.5, 0.5, 1.0], mode="trimmed_mean")
    if out_with > 0.55:
        fail(f"trimmed_mean leaked outlier: {out_with} > 0.55")
    ok(f"trimmed_mean robust against 1.0 outlier (got {out_with:.3f})")

    step("3. mean mode: includes outliers")
    out_mean = aggregate_confidence([0.5, 0.5, 0.5, 0.5, 1.0], mode="mean")
    if not (0.59 < out_mean < 0.61):
        fail(f"mean: expected ~0.6, got {out_mean}")
    ok(f"mean = {out_mean:.3f} (includes outlier — explicit override path)")

    step("4. NEGATIVE — clamp to [0, 1] no matter the input")
    if aggregate_confidence([1.5, 2.0]) > 1.0:
        fail("aggregate_confidence > 1.0 leaked")
    if aggregate_confidence([-1.0, -0.5]) < 0.0:
        fail("aggregate_confidence < 0.0 leaked")
    ok("clamp holds")

    step("5. small N (n=2) falls back to mean — no points to trim")
    out_two = aggregate_confidence([0.4, 0.8], mode="trimmed_mean")
    if abs(out_two - 0.6) > 0.001:
        fail(f"n=2 fallback wrong: {out_two}")
    ok(f"n=2 trimmed_mean falls back to mean = {out_two}")

    # ============================================================
    # Q2: Evidence checker
    # ============================================================
    step("6. cited claim → 'pass' verdict")
    v = check_evidence("HNSW reduces search latency. See [source: 2023 paper].")
    if v.decision != "pass":
        fail(f"cited claim flagged: {v}")
    ok(f"cited claim passes; cited={v.cited_count}")

    step("7. NEGATIVE — uncited claim → 'demote' verdict (not 'reject')")
    v = check_evidence("Caching saves 80% of cost. It is the best approach.")
    if v.decision != "demote":
        fail(f"default policy should demote, not {v.decision}")
    if v.demote_amount <= 0 or v.demote_amount > EVIDENCE_DEMOTE_MAX:
        fail(f"demote_amount out of range: {v.demote_amount}")
    if v.uncited_count == 0:
        fail("uncited_count should be > 0")
    ok(f"uncited demote_amount={v.demote_amount} uncited={v.uncited_count}")

    step("8. NEGATIVE — empty text → 'pass' (no false positives)")
    v = check_evidence("")
    if v.decision != "pass":
        fail(f"empty text false-positive: {v.decision}")
    if v.uncited_count != 0:
        fail("empty text reported uncited claims")
    ok("empty text → pass with 0 claims")

    step("9. reject mode (override): uncited claim → 'reject'")
    v = check_evidence(
        "Caching saves 80% of cost. It is the best approach.",
        policy="reject",
    )
    if v.decision != "reject":
        fail(f"reject policy not honored: {v.decision}")
    ok("reject policy override works")

    # ============================================================
    # Q3: Dissent detection
    # ============================================================
    step("10. consensus — all agents agree → has_dissent=False")
    same_text = "Use HNSW with M=16 and ef_construct=200. " * 8
    responses = [
        AgentResponse(role=f"agent_{i}", model="x", content=same_text,
                      tokens=10, latency_ms=10) for i in range(4)
    ]
    d = detect_dissent(responses)
    if d.has_dissent:
        fail(f"consensus flagged as dissent: {d}")
    ok(f"consensus correctly NOT flagged; sims={d.similarities}")

    step("11. NEGATIVE — 2 divergent agents trigger has_dissent=True")
    diverg = [
        AgentResponse(role="primary_expert", model="x",
                      content="Use HNSW with M=16 and ef_construct=200. " * 5,
                      tokens=10, latency_ms=10),
        AgentResponse(role="opponent", model="x",
                      content=("Throw away vector search entirely. "
                               "BM25 keyword retrieval is faster and simpler "
                               "with proper query expansion. "
                               "ElasticSearch BM25 dominates HNSW for short queries. " * 3),
                      tokens=10, latency_ms=10),
        AgentResponse(role="research", model="x",
                      content=("Lookup tables and pre-computed answers "
                               "skip retrieval entirely. "
                               "Cache hot queries in Redis directly. " * 3),
                      tokens=10, latency_ms=10),
    ]
    d = detect_dissent(diverg)
    if not d.has_dissent:
        fail(f"divergent agents NOT flagged as dissent: sims={d.similarities}")
    if len(d.dissenting_roles) < 2:
        fail(f"need ≥2 dissenting roles, got {d.dissenting_roles}")
    ok(f"dissent flagged: roles={d.dissenting_roles} sims={d.similarities}")

    step("12. NEGATIVE — n=1 cannot have dissent")
    d = detect_dissent([
        AgentResponse(role="solo", model="x", content="x",
                      tokens=1, latency_ms=1)
    ])
    if d.has_dissent:
        fail("n=1 cannot dissent")
    ok("n=1 → has_dissent=False")

    print(f"\n{BOLD}{GREEN}ALL 12 ROUND-MECHANICS STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
