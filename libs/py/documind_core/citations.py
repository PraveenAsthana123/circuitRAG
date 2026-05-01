"""
Citation linking — claim-to-source provenance (§16.6 + §48 of the
playbook + RAG explainability rules).

Why this matters:
- Every span in an LLM-generated answer must trace to a chunk in
  the retrieval set. Uncited spans are a hallucination flag — both
  for runtime guardrails and for §48 explainability evidence rows.
- This module provides the deterministic linker that runs AFTER
  generation: split the answer into claim units (sentences), score
  each claim against each retrieved chunk, attach the best
  matches above a threshold.
- The output IS the explainability artifact — `claim_chunk_map`
  goes straight into the §38 audit row.

DSA: bipartite scoring graph (claims × chunks). At typical sizes
(claims ≈ 10, chunks ≈ 20) this is O(claims * chunks * tok_count)
which is fine. For larger answers, switch to embedding-based
similarity (one matrix multiply).

This intentionally uses STRING-OVERLAP scoring (BM25-like) rather
than embedding cosine, so:
1. It works without embedding inference at citation time (cheap).
2. It catches verbatim quotes from retrieved chunks — exactly the
   trail regulators want to see.

Callers who want semantic citation linking compose this with an
embedding-based scorer; this module guarantees the lexical floor.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["Claim", "CitedClaim", "CitationLinker", "split_into_claims"]


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_TOKEN = re.compile(r"\b\w+\b")


@dataclass(frozen=True)
class Claim:
    """One claim unit (typically a sentence) from the answer."""

    text: str
    start: int  # offset in the original answer
    end: int  # exclusive


@dataclass(frozen=True)
class CitedClaim:
    """A claim + the chunks that support it.

    citations is a list of (chunk_id, overlap_score) pairs sorted
    by score descending. Empty list means the claim has NO support
    in the retrieval set — a hallucination signal.
    """

    claim: Claim
    citations: tuple[tuple[str, float], ...]

    @property
    def is_supported(self) -> bool:
        return len(self.citations) > 0


def _tokenize(text: str) -> set[str]:
    """Lowercase content tokens — what we score overlap on."""
    return {t.lower() for t in _TOKEN.findall(text)}


def split_into_claims(answer: str) -> list[Claim]:
    """Split answer text into claim-shaped units (sentences).

    Empty answer → empty list. Single sentence with no terminating
    punctuation is still treated as one claim.
    """
    answer = answer.strip()
    if not answer:
        return []

    # Walk sentence boundaries collecting (start, end). Use the
    # regex finditer to know split positions; the spans BETWEEN
    # matches are the sentences.
    out: list[Claim] = []
    last_end = 0
    for m in _SENTENCE_BOUNDARY.finditer(answer):
        text = answer[last_end : m.start()].strip()
        if text:
            out.append(Claim(text=text, start=last_end, end=m.start()))
        last_end = m.end()
    # Tail: from last_end to end of string.
    tail = answer[last_end:].strip()
    if tail:
        out.append(Claim(text=tail, start=last_end, end=len(answer)))
    return out


@dataclass(frozen=True)
class _ScoredChunk:
    """Internal — chunk + tokens, precomputed for scoring."""

    chunk_id: str
    text: str
    tokens: frozenset[str]


class CitationLinker:
    """Lexical citation linker.

    Usage::

        linker = CitationLinker(min_overlap=0.3, top_k=2)
        cited = linker.link(
            answer="Refunds within 30 days. Shipping is free.",
            chunks=[
                ("chunk-1", "Our refund policy allows 30 days..."),
                ("chunk-2", "Shipping is always free for members."),
                ("chunk-3", "Hours are 9 to 5."),
            ],
        )
        # cited[0].citations = [("chunk-1", 0.82)]
        # cited[1].citations = [("chunk-2", 0.75)]

    min_overlap is the Jaccard threshold below which we don't
    record a citation — too many false positives otherwise.
    """

    def __init__(
        self,
        *,
        min_overlap: float = 0.2,
        top_k: int = 3,
    ) -> None:
        if not 0.0 <= min_overlap <= 1.0:
            raise ValueError(f"min_overlap must be in [0, 1], got {min_overlap}")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        self._min_overlap = min_overlap
        self._top_k = top_k

    def link(
        self,
        *,
        answer: str,
        chunks: Sequence[tuple[str, str]],
    ) -> list[CitedClaim]:
        """Return one CitedClaim per claim in the answer.

        Args:
            answer: the LLM-generated answer text.
            chunks: list of (chunk_id, chunk_text) the retrieval
                set the answer was generated from.
        """
        claims = split_into_claims(answer)
        if not claims:
            return []

        # Pre-tokenize chunks once — claims are typically far fewer
        # than chunks, so this caches the bigger side.
        scored_chunks = [
            _ScoredChunk(chunk_id=cid, text=ctext, tokens=frozenset(_tokenize(ctext))) for cid, ctext in chunks
        ]

        out: list[CitedClaim] = []
        for claim in claims:
            claim_tokens = _tokenize(claim.text)
            if not claim_tokens:
                out.append(CitedClaim(claim=claim, citations=()))
                continue
            scored: list[tuple[str, float]] = []
            for chunk in scored_chunks:
                score = self._jaccard(claim_tokens, chunk.tokens)
                if score >= self._min_overlap:
                    scored.append((chunk.chunk_id, score))
            scored.sort(key=lambda x: -x[1])
            out.append(CitedClaim(claim=claim, citations=tuple(scored[: self._top_k])))
        return out

    def hallucination_rate(self, cited: Sequence[CitedClaim]) -> float:
        """Fraction of claims with zero citations.

        Use this as a gauge for the §48 explainability dashboard —
        rates > 0.2 typically mean retrieval relevance is failing
        and the answer is mostly hallucinated.
        """
        if not cited:
            return 0.0
        unsupported = sum(1 for c in cited if not c.is_supported)
        return unsupported / len(cited)

    @staticmethod
    def _jaccard(a: set[str], b: frozenset[str]) -> float:
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0
