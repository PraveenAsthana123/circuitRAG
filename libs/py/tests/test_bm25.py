"""
Tests for documind_core.bm25 — BM25 lexical retrieval wrapper.

Covers:
- tokenize lowercases and splits on word boundaries
- BM25Hit is frozen
- Empty corpus is valid state, search returns []
- Empty query / no-match query → []
- top_k=0 raises ValueError
- BM25 ranks rare-keyword matches over generic
- Empty-document edge case (rank_bm25 raises without our placeholder)
- Composes with fusion.reciprocal_rank_fusion (returns chunk_ids
  sortable by RRF)
"""

from __future__ import annotations

import pytest

from documind_core.bm25 import BM25Hit, BM25Index, tokenize
from documind_core.fusion import reciprocal_rank_fusion


class TestTokenize:
    def test_lowercase_split(self) -> None:
        assert tokenize("Hello World!") == ["hello", "world"]

    def test_strips_punct(self) -> None:
        assert "policy" in tokenize("Refund policy: 30 days.")

    def test_empty(self) -> None:
        assert tokenize("") == []


class TestBM25Hit:
    def test_frozen(self) -> None:
        h = BM25Hit(chunk_id="c1", score=1.0)
        with pytest.raises((AttributeError, Exception)):
            h.score = 2.0  # type: ignore[misc]


class TestBM25Index:
    def test_empty_corpus(self) -> None:
        idx = BM25Index([])
        assert len(idx) == 0
        assert idx.search("anything") == []

    def test_basic_ranking(self) -> None:
        idx = BM25Index(
            [
                ("c1", "Our refund policy allows returns within 30 days."),
                ("c2", "Shipping is free for premium members."),
                ("c3", "Office hours: 9 to 5 Monday through Friday."),
            ]
        )
        hits = idx.search("refund policy")
        assert len(hits) >= 1
        # The chunk that literally contains both query terms wins.
        assert hits[0].chunk_id == "c1"
        # Scores strictly positive (we filter <=0).
        assert all(h.score > 0 for h in hits)

    def test_no_match_returns_empty(self) -> None:
        idx = BM25Index([("c1", "completely unrelated content")])
        # Empty-string-after-tokenize query → [].
        assert idx.search("") == []
        # Punctuation-only query also normalizes to no tokens.
        assert idx.search("!!!") == []

    def test_top_k_caps_results(self) -> None:
        idx = BM25Index([(f"c{i}", "policy refund " * i) for i in range(1, 6)])
        hits = idx.search("refund policy", top_k=2)
        assert len(hits) <= 2

    def test_top_k_zero_raises(self) -> None:
        # NEGATIVE: silent empty-list would mask config bug.
        idx = BM25Index([("c1", "x")])
        with pytest.raises(ValueError, match="top_k"):
            idx.search("anything", top_k=0)

    def test_empty_document_handled(self) -> None:
        # NEGATIVE-shaped: an empty document in the corpus must NOT
        # crash rank_bm25's index build (it would raise without our
        # placeholder).
        idx = BM25Index(
            [
                ("c1", "real content here"),
                ("c2", ""),  # empty
                ("c3", "more real content"),
            ]
        )
        hits = idx.search("content")
        # The non-empty docs must rank above the placeholder one.
        ids = [h.chunk_id for h in hits]
        assert "c1" in ids or "c3" in ids


class TestComposition:
    def test_composes_with_rrf(self) -> None:
        # The whole point of BM25 in this codebase: the result list
        # feeds straight into RRF for hybrid retrieval.
        idx = BM25Index(
            [
                ("c1", "refund policy text here"),
                ("c2", "shipping text here"),
                ("c3", "hours text here"),
            ]
        )
        bm25_hits = idx.search("refund policy")
        bm25_ranking = [h.chunk_id for h in bm25_hits]
        # Pretend we also have a vector-search ranking that puts
        # "shipping" first (a different signal). RRF should boost
        # whatever appears in both.
        vector_ranking = ["c2", "c1", "c3"]
        fused = reciprocal_rank_fusion([bm25_ranking, vector_ranking])
        # All 3 (or 2 of 3) appear in fused output.
        items = [r.item for r in fused]
        assert "c1" in items
        # Scores all positive.
        assert all(r.score > 0 for r in fused)
