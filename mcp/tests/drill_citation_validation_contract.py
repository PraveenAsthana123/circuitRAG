# RESOURCES: readonly
"""
Drill: citation linker contract — closes the §48.5 RAG explainability
four-part contract (retrieval trail + prompt rendering + CITATION
mapping + guardrail trace).

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
one-thing-per-iter), §45.4 (no checkbox flips without code), §39.5
(RAG explainability four-part contract), §48 (AI explainability), §48.5
(citation rule: every claim must trace to a chunk in the retrieval set;
uncited spans = hallucination flag), §47 (architecture: citation
linking is a separate concern from retrieval).

User's Environment State doc listed Citation Validation as ❌ Missing
in section 5 (RAG state). Empirical truth: libs/py/documind_core/citations.py
already exists with the full linker contract. Iter-57 ships the drill
that locks the contract going forward — the next time the matrix is
regenerated, the drill is the source of truth.

Locks (positive):
  L1. CitationLinker class importable + instantiable
  L2. link(answer=…, chunks=…) returns one CitedClaim per claim
      (claim count from split_into_claims should match return list)
  L3. CitedClaim.is_supported property is True when citations exist
  L4. hallucination_rate() returns fraction of unsupported claims
      ∈ [0.0, 1.0]
  L5. Verbatim quote from a chunk → cited (lexical floor held)

Locks (negative — ≥3 per §43):
  N1. min_overlap=0.0 raises ValueError (invalid threshold rejected)
  N2. min_overlap=1.5 raises ValueError (invalid threshold rejected)
  N3. top_k=0 raises ValueError (invalid limit rejected)
  N4. Empty answer → empty cited list (boundary case; no spurious citations)
  N5. Claim with NO overlap to ANY chunk → citations=() AND
      is_supported=False (hallucination flag triggered)
  N6. Wrong-chunk attribution suppressed: a claim that overlaps
      chunk A but NOT chunk B should cite A only, not B (cross-chunk
      contamination = wrong-attribution risk for §38 audit row)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    from documind_core.citations import (
        CitationLinker,
        CitedClaim,
        Claim,
        split_into_claims,
    )

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: CitationLinker importable + instantiable
    # ------------------------------------------------------------------
    step("1. CitationLinker importable + instantiable")
    linker = CitationLinker(min_overlap=0.2, top_k=3)
    if not isinstance(linker, CitationLinker):
        fail("CitationLinker construction failed")
    ok("CitationLinker(min_overlap=0.2, top_k=3) instantiated")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: link() returns one CitedClaim per claim
    # ------------------------------------------------------------------
    step("2. link() returns one CitedClaim per claim")
    # Tokens in answer must overlap chunks at Jaccard >= min_overlap (0.2).
    # Singular/plural divergence (refunds vs refund) breaks Jaccard, so
    # the fixtures use the same surface form across answer + chunk.
    answer = "Refund policy allows 30 days. Shipping is free."
    chunks = [
        ("chunk-1", "Our refund policy allows 30 days from purchase date."),
        ("chunk-2", "Shipping is free for all orders over $50."),
        ("chunk-3", "Office hours are 9 to 5 weekdays."),
    ]
    claims = split_into_claims(answer)
    cited = linker.link(answer=answer, chunks=chunks)
    if len(cited) != len(claims):
        fail(
            f"len(cited)={len(cited)} != len(claims)={len(claims)} — "
            f"linker dropped or duplicated claims"
        )
    if not all(isinstance(c, CitedClaim) for c in cited):
        fail("link() returned non-CitedClaim items")
    ok(f"link() returned {len(cited)} CitedClaim entries (1 per claim)")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: is_supported True when citations exist
    # ------------------------------------------------------------------
    step("3. CitedClaim.is_supported reflects citation presence")
    refund_cited = next(
        (c for c in cited if "refund" in c.claim.text.lower()
         or "policy" in c.claim.text.lower()), None,
    )
    if refund_cited is None:
        fail("could not locate the refund claim in cited list")
    if not refund_cited.is_supported:
        fail(
            f"refund claim should be supported (matches chunk-1); "
            f"got citations={refund_cited.citations}"
        )
    if refund_cited.citations[0][0] != "chunk-1":
        fail(
            f"refund claim should cite chunk-1; "
            f"got top citation={refund_cited.citations[0]}"
        )
    ok(f"is_supported=True; cites chunk-1 with score "
       f"{refund_cited.citations[0][1]:.2f}")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: hallucination_rate ∈ [0, 1]
    # ------------------------------------------------------------------
    step("4. hallucination_rate() returns fraction in [0, 1]")
    rate = linker.hallucination_rate(cited)
    if not isinstance(rate, float):
        fail(f"hallucination_rate returned non-float: {type(rate)}")
    if not 0.0 <= rate <= 1.0:
        fail(f"hallucination_rate={rate} outside [0, 1]")
    # In our test, both claims should be supported → rate=0.0
    if rate != 0.0:
        fail(
            f"hallucination_rate should be 0.0 (both claims grounded); "
            f"got {rate}"
        )
    ok(f"hallucination_rate=0.0 (both claims grounded); range valid")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: verbatim quote → cited (lexical floor)
    # ------------------------------------------------------------------
    step("5. POSITIVE: verbatim quote from a chunk gets cited")
    verbatim_answer = "Office hours are 9 to 5 weekdays."
    verbatim_chunks = [
        ("chunk-A", "Office hours are 9 to 5 weekdays."),
        ("chunk-B", "Pricing is competitive."),
    ]
    v_cited = linker.link(answer=verbatim_answer, chunks=verbatim_chunks)
    if not v_cited or not v_cited[0].is_supported:
        fail("verbatim quote not cited — lexical floor broken")
    if v_cited[0].citations[0][0] != "chunk-A":
        fail(
            f"verbatim quote should cite chunk-A; got "
            f"{v_cited[0].citations[0][0]}"
        )
    ok("verbatim quote correctly cites the source chunk")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: invalid min_overlap threshold rejected
    # ------------------------------------------------------------------
    step("6. NEGATIVE: invalid min_overlap rejected")
    for bad in (-0.1, 1.5, 2.0):
        try:
            CitationLinker(min_overlap=bad)
            fail(
                f"CitationLinker(min_overlap={bad}) should raise "
                f"ValueError; threshold out of [0, 1]"
            )
        except ValueError:
            pass
    ok("min_overlap outside [0, 1] raises ValueError (3 cases)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: invalid top_k rejected
    # ------------------------------------------------------------------
    step("7. NEGATIVE: invalid top_k rejected")
    for bad in (0, -1):
        try:
            CitationLinker(top_k=bad)
            fail(
                f"CitationLinker(top_k={bad}) should raise ValueError; "
                f"top_k must be >= 1"
            )
        except ValueError:
            pass
    ok("top_k <= 0 raises ValueError (2 cases)")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: empty answer → empty cited list
    # ------------------------------------------------------------------
    step("8. NEGATIVE: empty answer → empty cited list (no spurious citations)")
    empty_cited = linker.link(answer="", chunks=chunks)
    if empty_cited:
        fail(
            f"empty answer should yield empty cited list; "
            f"got {len(empty_cited)} entries"
        )
    whitespace_cited = linker.link(answer="   \n  ", chunks=chunks)
    if whitespace_cited:
        fail(f"whitespace-only answer should yield empty list")
    ok("empty + whitespace-only answers → 0 citations (boundary held)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: hallucinated claim → unsupported (no citations)
    # ------------------------------------------------------------------
    step("9. NEGATIVE: hallucinated claim → is_supported=False")
    hallucinated_answer = (
        "Quantum computers solve traveling salesman in linear time."
    )
    h_chunks = [
        ("chunk-X", "Our refund policy allows 30 days."),
        ("chunk-Y", "Shipping is free for orders over $50."),
    ]
    h_cited = linker.link(answer=hallucinated_answer, chunks=h_chunks)
    if not h_cited:
        fail("split_into_claims dropped the hallucinated answer")
    if h_cited[0].is_supported:
        fail(
            "hallucinated claim flagged as supported — explainability "
            "contract broken (uncited span MUST be hallucination flag)"
        )
    if h_cited[0].citations:
        fail(
            f"hallucinated claim should have NO citations; "
            f"got {h_cited[0].citations}"
        )
    h_rate = linker.hallucination_rate(h_cited)
    if h_rate != 1.0:
        fail(f"hallucination_rate should be 1.0 (all unsupported); got {h_rate}")
    ok(f"hallucinated claim → is_supported=False; "
       f"hallucination_rate=1.0 (full flag)")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: wrong-chunk attribution suppressed
    # ------------------------------------------------------------------
    step("10. NEGATIVE: claim citing chunk A does NOT also cite irrelevant chunk B")
    crisp_answer = "The capital of France is Paris."
    crisp_chunks = [
        ("chunk-A", "Paris is the capital of France since 987 AD."),
        ("chunk-B", "Bananas are yellow when ripe."),
    ]
    c_cited = linker.link(answer=crisp_answer, chunks=crisp_chunks)
    if not c_cited:
        fail("split_into_claims dropped the crisp answer")
    cited_ids = [cid for cid, _ in c_cited[0].citations]
    if "chunk-A" not in cited_ids:
        fail(
            f"crisp claim should cite chunk-A; got {cited_ids}"
        )
    if "chunk-B" in cited_ids:
        fail(
            f"crisp claim wrongly attributed to chunk-B (about bananas) — "
            f"cross-chunk contamination = wrong-attribution risk for "
            f"§38 audit row. Got citations={c_cited[0].citations}"
        )
    ok("crisp claim cites chunk-A only; chunk-B (irrelevant) suppressed")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
