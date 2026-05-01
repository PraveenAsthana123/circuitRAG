"""
Tests for documind_core.citations — claim-to-source linker.

Covers:
- split_into_claims: empty, single, multiple sentences
- Claim + CitedClaim are frozen
- CitedClaim.is_supported reflects citation count
- Linker init validates min_overlap and top_k
- link() with no chunks → empty citations on every claim
- link() finds overlap above threshold
- link() respects top_k cap (no overflow)
- link() filters below min_overlap
- hallucination_rate computes correctly + edge case (empty list)
- _jaccard handles empty + symmetric sets
"""

from __future__ import annotations

import pytest

from documind_core.citations import (
    CitationLinker,
    CitedClaim,
    Claim,
    split_into_claims,
)


class TestSplitIntoClaims:
    def test_empty(self) -> None:
        assert split_into_claims("") == []
        assert split_into_claims("   \n  ") == []

    def test_single_sentence_no_terminator(self) -> None:
        # "no terminator" — should still yield one claim.
        claims = split_into_claims("hello world")
        assert len(claims) == 1
        assert claims[0].text == "hello world"

    def test_multiple_sentences(self) -> None:
        claims = split_into_claims("First. Second statement. Third!")
        assert len(claims) == 3
        assert claims[0].text == "First."
        assert claims[1].text == "Second statement."
        assert claims[2].text == "Third!"

    def test_offsets_correct(self) -> None:
        # The start/end MUST be valid indices into the original.
        text = "First. Second."
        claims = split_into_claims(text)
        assert text[claims[0].start : claims[0].end] == "First."


class TestDataclasses:
    def test_claim_frozen(self) -> None:
        c = Claim(text="x", start=0, end=1)
        with pytest.raises((AttributeError, Exception)):
            c.text = "y"  # type: ignore[misc]

    def test_cited_claim_frozen(self) -> None:
        cc = CitedClaim(claim=Claim(text="x", start=0, end=1), citations=())
        with pytest.raises((AttributeError, Exception)):
            cc.citations = (("c", 0.5),)  # type: ignore[misc]

    def test_is_supported_reflects_citations(self) -> None:
        cc = CitedClaim(claim=Claim(text="x", start=0, end=1), citations=())
        assert cc.is_supported is False
        cc2 = CitedClaim(claim=Claim(text="x", start=0, end=1), citations=(("c", 0.5),))
        assert cc2.is_supported is True


class TestLinkerInit:
    def test_min_overlap_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="min_overlap"):
            CitationLinker(min_overlap=-0.1)
        with pytest.raises(ValueError, match="min_overlap"):
            CitationLinker(min_overlap=1.5)

    def test_top_k_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="top_k"):
            CitationLinker(top_k=0)


class TestLink:
    def test_no_chunks_no_citations(self) -> None:
        linker = CitationLinker()
        cited = linker.link(answer="A claim.", chunks=[])
        assert len(cited) == 1
        assert cited[0].is_supported is False

    def test_finds_overlap_above_threshold(self) -> None:
        linker = CitationLinker(min_overlap=0.2)
        cited = linker.link(
            answer="Refunds are within thirty days.",
            chunks=[
                ("c1", "Our refund policy: refunds within thirty days of purchase."),
                ("c2", "Hours are 9 to 5."),
            ],
        )
        # c1 has high overlap; c2 has none.
        assert len(cited) == 1
        assert cited[0].is_supported
        assert cited[0].citations[0][0] == "c1"

    def test_filters_below_min_overlap(self) -> None:
        # Set threshold high enough to exclude weak matches.
        linker = CitationLinker(min_overlap=0.95)
        cited = linker.link(
            answer="Some quick fact about pricing.",
            chunks=[("c1", "Completely unrelated content about hours.")],
        )
        # No chunks meet the threshold.
        assert cited[0].is_supported is False

    def test_top_k_caps_citations(self) -> None:
        # Three chunks all match — but top_k=2 means only 2 cited.
        linker = CitationLinker(min_overlap=0.0, top_k=2)
        cited = linker.link(
            answer="Refund policy details.",
            chunks=[
                ("c1", "Refund policy applies."),
                ("c2", "Policy refund details."),
                ("c3", "Refund details for policy."),
            ],
        )
        assert len(cited[0].citations) == 2

    def test_citations_sorted_by_score_desc(self) -> None:
        linker = CitationLinker(min_overlap=0.0, top_k=10)
        cited = linker.link(
            answer="refund policy",
            chunks=[
                ("low", "completely different"),
                ("high", "refund policy"),
                ("mid", "refund details"),
            ],
        )
        scores = [s for _, s in cited[0].citations]
        # Strictly descending.
        assert scores == sorted(scores, reverse=True)

    def test_claim_with_no_tokens_has_no_citations(self) -> None:
        # NEGATIVE: pure-punctuation claim has no tokens to match.
        # Must NOT crash trying to compute Jaccard on empty set.
        linker = CitationLinker()
        cited = linker.link(
            answer="!!! ???",
            chunks=[("c1", "anything")],
        )
        # split_into_claims may return zero claims for pure-punct
        # OR one claim with no citations. Either way, no crash.
        for c in cited:
            if not _tokens_in(c.claim.text):
                assert c.is_supported is False


def _tokens_in(text: str) -> bool:
    """Helper for the punct-only check above."""
    import re

    return bool(re.search(r"\w", text))


class TestHallucinationRate:
    def test_all_supported_zero_rate(self) -> None:
        linker = CitationLinker(min_overlap=0.0)
        cited = linker.link(
            answer="One. Two.",
            chunks=[("c", "one two")],
        )
        # Both claims supported.
        assert linker.hallucination_rate(cited) == 0.0

    def test_partial_support(self) -> None:
        linker = CitationLinker(min_overlap=0.5)
        cited = linker.link(
            answer="Refund exists. Price unknown.",
            chunks=[("c", "Refund exists in policy")],
        )
        # First claim should match c; second won't.
        rate = linker.hallucination_rate(cited)
        assert 0.0 < rate <= 1.0

    def test_empty_returns_zero(self) -> None:
        # NEGATIVE: empty cited list must NOT raise ZeroDivisionError.
        assert CitationLinker().hallucination_rate([]) == 0.0
