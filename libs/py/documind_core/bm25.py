"""
BM25 lexical retrieval — wraps `rank_bm25` for the hybrid-retrieval
BM25 layer (§16.5 + §1.4 of the playbook).

Why include BM25 alongside vector retrieval:
- Vector retrieval generalizes via semantic similarity but misses
  rare-keyword queries (model numbers, product codes, exact
  phrasing). BM25 is the lexical floor that catches these.
- RRF (in `fusion.py`) fuses BM25 + vector + graph rankings
  without needing score normalization (§16.5).
- BM25 is CHEAP — pure CPU, no GPU/embedder required. Adds <10ms
  per query to a 100-doc corpus.

DSA: inverted index + per-term IDF + per-doc length normalization.
The `rank_bm25` library provides BM25Okapi which is the standard
production variant. Index build is O(n * avg_doc_len); query is
O(query_terms * docs_with_term).

This module is a THIN wrapper that:
1. Adopts our `Chunk` dataclass shape (the `chunking.py` Chunk).
2. Versions the index (chunker_version travels with stored corpus).
3. Tokenizes via the same regex as the rest of the codebase
   (consistent with `pii.py` / `query_rewriter.py`).
4. Returns ranked (chunk_id, score) tuples that compose with
   `fusion.reciprocal_rank_fusion`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["BM25Index", "BM25Hit", "tokenize"]


_TOKEN = re.compile(r"\b\w+\b")


def tokenize(text: str) -> list[str]:
    """Lowercase content tokens. Same regex used elsewhere in
    this codebase for consistency (PII scanner, query rewriter)."""
    return [t.lower() for t in _TOKEN.findall(text)]


@dataclass(frozen=True)
class BM25Hit:
    """One BM25 result. Frozen so it's safe in caches + audit rows."""

    chunk_id: str
    score: float


class BM25Index:
    """In-memory BM25 index over (chunk_id, text) pairs.

    Lifecycle:
    - Build at ingestion time (or service startup) from the corpus.
    - Query at retrieval time.
    - Rebuild on chunker_version change (caller's contract).

    NOT durable — operators who need persistence should serialize
    the index alongside its (chunker_version, model) namespace OR
    rebuild at service start from Postgres.

    Usage::

        idx = BM25Index([
            ("c1", "Refund policy: returns within 30 days."),
            ("c2", "Shipping is free for members."),
            ("c3", "Hours: 9-5 Mon-Fri."),
        ])
        hits = idx.search("refund window", top_k=2)
        # [BM25Hit(chunk_id="c1", score=...), ...]
    """

    def __init__(
        self,
        corpus: Sequence[tuple[str, str]],
    ) -> None:
        # Lazy-import the dep so the rest of documind_core doesn't
        # require rank_bm25 — only callers that touch this module
        # pay the import cost.
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError(
                "BM25Index requires the 'rank_bm25' package. " "Install via `pip install rank_bm25`."
            ) from exc

        if not corpus:
            # Empty corpus is a valid state — search returns [].
            # We still construct the underlying object so .search
            # doesn't have to branch.
            self._chunk_ids: list[str] = []
            self._bm25 = None
            return

        self._chunk_ids = [cid for cid, _t in corpus]
        tokenized_docs = [tokenize(text) for _cid, text in corpus]
        # rank_bm25 raises if any doc is empty (zero tokens). Replace
        # empty docs with a single placeholder so the index builds
        # but the doc has very low BM25 weight.
        tokenized_docs = [doc if doc else ["__empty__"] for doc in tokenized_docs]
        self._bm25 = BM25Okapi(tokenized_docs)

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def search(self, query: str, *, top_k: int = 10) -> list[BM25Hit]:
        """Return top-K most-relevant hits. Empty query → [].

        top_k must be >= 1 (silent empty-list would mask config bugs).
        """
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if not query or not self._bm25 or not self._chunk_ids:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        # At typical N=100..10K and top_k=10 a sort is fine.
        # Switch to heap-based top_k from fusion.py if N > 1M.
        ranked = sorted(
            zip(self._chunk_ids, scores, strict=True),
            key=lambda x: -x[1],
        )
        # Drop scores <= 0 (no overlap) — they're noise.
        out = [BM25Hit(chunk_id=cid, score=float(s)) for cid, s in ranked if s > 0]
        return out[:top_k]
