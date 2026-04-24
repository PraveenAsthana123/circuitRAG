"""
Recursive character-based chunker.

Algorithm
---------
Given a target chunk size (in tokens) and a list of separators ordered from
most-preferred (paragraph) to least-preferred (word):

1. If the text fits under the budget → return as one chunk.
2. Otherwise, find the best separator that lets us cut at the largest
   natural boundary while staying under budget.
3. Recurse on the pieces that still exceed budget.

Overlap handling: after the split, we prepend the trailing ``overlap_tokens``
of chunk N to chunk N+1, so queries that match the boundary still find both.

Deliberately NOT using LangChain here
------------------------------------
LangChain's ``RecursiveCharacterTextSplitter`` does the same thing. We
reimplement for three reasons:

1. One fewer heavy dependency — LangChain pulls in everything.
2. We need token-aware splitting (LangChain defaults to char-aware).
3. Learning: this is exactly the kind of building block worth
   understanding, not importing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.parsers import ParsedDocument, ParsedPage

from .base import Chunk, Chunker
from .token_counter import TokenCounter

log = logging.getLogger(__name__)


@dataclass
class _Piece:
    text: str
    page_number: int


class RecursiveChunker(Chunker):
    """
    Token-aware recursive chunker.

    Args:
        target_tokens: The chunk-size budget. Hits, exceeds only if no
            separator works within the budget.
        overlap_tokens: Tokens copied from the end of chunk N into the start
            of chunk N+1. 10-20% of ``target_tokens`` is the sweet spot.
        separators: Preference-ordered list. Default is paragraph → line →
            sentence → word → character.
        counter: Optional shared :class:`TokenCounter`.
    """

    DEFAULT_SEPARATORS: tuple[str, ...] = (
        "\n\n",   # paragraph
        "\n",     # line
        ". ",     # sentence (approx — good enough for RAG)
        "? ",
        "! ",
        "; ",
        ", ",
        " ",      # word
        "",       # char
    )

    def __init__(
        self,
        target_tokens: int = 512,
        overlap_tokens: int = 50,
        separators: tuple[str, ...] | None = None,
        counter: TokenCounter | None = None,
    ) -> None:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be > 0")
        if overlap_tokens >= target_tokens:
            raise ValueError("overlap_tokens must be < target_tokens")
        self._target = target_tokens
        self._overlap = overlap_tokens
        self._separators = separators or self.DEFAULT_SEPARATORS
        self._counter = counter or TokenCounter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        raw_pieces: list[_Piece] = []
        for page in document.pages:
            for piece in self._split_page(page):
                raw_pieces.append(piece)

        chunks = self._apply_overlap(raw_pieces)

        log.info(
            "chunked pages=%d raw=%d final=%d target=%d overlap=%d",
            len(document.pages), len(raw_pieces), len(chunks), self._target, self._overlap,
        )
        return chunks

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------
    def _split_page(self, page: ParsedPage) -> list[_Piece]:
        if not page.text.strip():
            return []
        if self._counter.count(page.text) <= self._target:
            return [_Piece(text=page.text.strip(), page_number=page.page_number)]
        return [
            _Piece(text=t, page_number=page.page_number)
            for t in self._recursive_split(page.text)
        ]

    def _recursive_split(self, text: str) -> list[str]:
        """Core recursion: try separators in order, split at the best fit."""
        if self._counter.count(text) <= self._target:
            return [text]

        for sep in self._separators:
            if sep == "" or sep in text:
                parts = text.split(sep) if sep else [text]
                # Re-introduce the separator at the end of each part except the last
                rejoined = [p + (sep if i < len(parts) - 1 else "") for i, p in enumerate(parts)]
                merged = self._merge_within_budget(rejoined)
                # If merging produced >1 piece, recurse on each oversize piece
                if len(merged) > 1 or (len(merged) == 1 and self._counter.count(merged[0]) <= self._target):
                    out: list[str] = []
                    for piece in merged:
                        if self._counter.count(piece) <= self._target:
                            out.append(piece)
                        else:
                            out.extend(self._recursive_split(piece))
                    return out
        # Fall-through: hard-cut by tokens
        return self._counter.split_by_tokens(text, self._target)

    def _merge_within_budget(self, parts: list[str]) -> list[str]:
        """Greedily combine consecutive parts while staying under budget."""
        out: list[str] = []
        buf = ""
        for part in parts:
            candidate = buf + part
            if self._counter.count(candidate) <= self._target:
                buf = candidate
            else:
                if buf:
                    out.append(buf)
                buf = part
        if buf:
            out.append(buf)
        return out

    def _apply_overlap(self, pieces: list[_Piece]) -> list[Chunk]:
        """Produce final :class:`Chunk` list with tail-overlap from the
        previous chunk prepended to each chunk."""
        chunks: list[Chunk] = []
        for i, piece in enumerate(pieces):
            text = piece.text.strip()
            if not text:
                continue
            if i > 0 and self._overlap > 0:
                prev = pieces[i - 1].text
                prev_tokens = self._counter._encoding.encode(prev, disallowed_special=())
                tail = self._counter._encoding.decode(prev_tokens[-self._overlap:])
                text = tail + " " + text

            token_count = self._counter.count(text)
            chunks.append(
                Chunk(
                    content_hash=Chunk.hash_content(text),
                    index=len(chunks),
                    text=text,
                    token_count=token_count,
                    page_number=piece.page_number,
                    metadata={
                        "chunker": "recursive",
                        "target_tokens": self._target,
                        "overlap_tokens": self._overlap,
                    },
                )
            )
        return chunks
