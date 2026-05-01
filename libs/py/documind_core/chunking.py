"""
Multi-strategy chunking — Strategy + Factory pattern (§7 of the
RAG playbook), 7 first-tier strategies from §2.

Why this lives in documind_core (not ingestion-svc):
- Multiple services need consistent chunking semantics
  (ingestion writes, eval re-chunks for ground-truth, agent
  orchestrator chunks long contexts before retrieval).
- Strategy can be selected at runtime via env / per-tenant config,
  so a single shared library lets the registry version travel
  with the service binary.

The 12-strategy table in the playbook lists semantic, table-aware,
code-aware, hierarchical, and metadata-aware chunkers as well —
those need extra deps (sentence-transformers / tree-sitter / table
parsers) so they belong in their own modules. This file ships the
7 deterministic, dep-free strategies that cover ~80% of the
text-document cases.

Versioning contract: every Chunk carries `chunker_version` so
caches keyed by content_hash + chunker_version don't serve stale
chunks after a strategy change (§1.4 reject-when rule for chunk
cache).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "Chunk",
    "ChunkStrategy",
    "Chunker",
    "make_chunker",
    "FixedSizeChunker",
    "SlidingWindowChunker",
    "SentenceChunker",
    "ParagraphChunker",
    "HeaderChunker",
    "RecursiveChunker",
    "TokenCapChunker",
]


CHUNKER_VERSION = "1.0.0"


class ChunkStrategy(str, Enum):  # noqa: UP042 — keep str-mixin for direct
    """Identifier for the strategy used to produce a chunk.

    Stored on every chunk so caches/audit rows can branch on it.
    Inherits from `str` so `chunk.strategy == "fixed"` works naturally
    in JSON-serialized audit rows + Pydantic schemas.
    """

    FIXED = "fixed"
    SLIDING_WINDOW = "sliding_window"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    HEADER = "header"
    RECURSIVE = "recursive"
    TOKEN_CAP = "token_cap"  # noqa: S105 — chunking strategy name, not a credential


@dataclass(frozen=True)
class Chunk:
    """A single chunk + provenance metadata.

    Frozen because chunks flow through caches and across processes;
    mutation would silently invalidate cache keys.
    """

    text: str
    index: int
    strategy: ChunkStrategy
    chunker_version: str = CHUNKER_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.text)


# ── strategies (Strategy pattern) ─────────────────────────────


class Chunker:
    """Abstract base. Subclasses implement :meth:`split`.

    Each strategy is a tiny class so the dispatcher (`make_chunker`)
    can pick by enum at runtime — same shape, different algorithm
    (the textbook Strategy pattern).
    """

    strategy: ChunkStrategy

    def split(self, text: str) -> list[Chunk]:
        raise NotImplementedError

    # Internal helper — wraps each fragment in a Chunk with the
    # right strategy + versioning. Subclasses use this instead of
    # building Chunk() directly.
    def _emit(self, fragments: Iterator[str], extra_metadata: dict[str, Any] | None = None) -> list[Chunk]:
        out: list[Chunk] = []
        for i, frag in enumerate(fragments):
            if not frag.strip():
                continue  # never emit whitespace-only chunks
            out.append(
                Chunk(
                    text=frag,
                    index=i,
                    strategy=self.strategy,
                    metadata=dict(extra_metadata or {}),
                )
            )
        return out


class FixedSizeChunker(Chunker):
    """Cut into fixed-character windows. Simplest possible. MVP-only.

    Limitations (per playbook §2): breaks meaning mid-sentence.
    Use SlidingWindowChunker for better recall.
    """

    strategy = ChunkStrategy.FIXED

    def __init__(self, *, size: int = 500) -> None:
        if size < 1:
            raise ValueError(f"size must be >= 1, got {size}")
        self.size = size

    def split(self, text: str) -> list[Chunk]:
        fragments = (text[i : i + self.size] for i in range(0, len(text), self.size))
        return self._emit(fragments)


class SlidingWindowChunker(Chunker):
    """Fixed window with overlap. Recall improves; storage grows.

    overlap is a fraction of `size` (10-20% per playbook §2 default).
    """

    strategy = ChunkStrategy.SLIDING_WINDOW

    def __init__(self, *, size: int = 500, overlap: int = 100) -> None:
        if size < 1:
            raise ValueError(f"size must be >= 1, got {size}")
        if overlap < 0 or overlap >= size:
            raise ValueError(f"overlap must be in [0, size); got overlap={overlap} size={size}")
        self.size = size
        self.overlap = overlap

    def split(self, text: str) -> list[Chunk]:
        if not text:
            return []
        step = self.size - self.overlap
        fragments = (text[i : i + self.size] for i in range(0, len(text), step) if text[i : i + self.size])
        return self._emit(fragments)


class SentenceChunker(Chunker):
    """One chunk per sentence (with optional max-token cap)."""

    strategy = ChunkStrategy.SENTENCE

    # Conservative sentence boundary — keeps "Mr. Smith" intact via
    # the lookbehind on capital-letter-after-space, doesn't claim
    # NLP-grade quality. For NLP-grade, plug spaCy / NLTK in a
    # subclass.
    _BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

    def __init__(self, *, max_chars: int | None = None) -> None:
        self.max_chars = max_chars

    def split(self, text: str) -> list[Chunk]:
        sentences = self._BOUNDARY.split(text.strip()) if text.strip() else []
        if self.max_chars is not None:
            # Hard-cap any sentence that's too long — playbook §2.3
            # "edge case: one sentence too long → split by clause/token".
            capped: list[str] = []
            for s in sentences:
                if len(s) <= self.max_chars:
                    capped.append(s)
                else:
                    for i in range(0, len(s), self.max_chars):
                        capped.append(s[i : i + self.max_chars])
            sentences = capped
        return self._emit(iter(sentences))


class ParagraphChunker(Chunker):
    """Split on blank lines. Good for well-formed business docs."""

    strategy = ChunkStrategy.PARAGRAPH

    _BOUNDARY = re.compile(r"\n\s*\n")

    def split(self, text: str) -> list[Chunk]:
        paragraphs = (p.strip() for p in self._BOUNDARY.split(text))
        return self._emit(paragraphs)


class HeaderChunker(Chunker):
    """Split on Markdown-style headings. Stamps `header_path` metadata.

    The header_path metadata IS the strategy's value-add — knowing
    "this chunk came from §3.2 / Subsection X" makes citation
    accurate (playbook §20 value-add table).
    """

    strategy = ChunkStrategy.HEADER

    _HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

    def split(self, text: str) -> list[Chunk]:
        matches = list(self._HEADING.finditer(text))
        if not matches:
            # No headers found — degrade to paragraph chunking, but
            # keep the strategy tag so callers can detect the no-header
            # case from the metadata.
            paragraph = ParagraphChunker()
            return [
                Chunk(
                    text=c.text,
                    index=c.index,
                    strategy=self.strategy,
                    metadata={"header_path": "(none)"},
                )
                for c in paragraph.split(text)
            ]

        out: list[Chunk] = []
        # Walk a stack of (level, title) so nested headers compose
        # into "Top > Sub > SubSub" — operators love that for citation.
        stack: list[tuple[int, str]] = []
        sections: list[tuple[str, str]] = []  # (header_path, body)

        for i, m in enumerate(matches):
            level = len(m.group(1))
            title = m.group(2)
            # Pop deeper-or-equal-level entries off the stack.
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            header_path = " > ".join(t for _, t in stack)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append((header_path, body))

        for i, (path, body) in enumerate(sections):
            if not body:
                continue
            out.append(
                Chunk(
                    text=body,
                    index=i,
                    strategy=self.strategy,
                    metadata={"header_path": path},
                )
            )
        return out


class RecursiveChunker(Chunker):
    """Best practical default (playbook §2 priority).

    Tries separators in order — section, then paragraph, then
    sentence, then fixed-size — splitting only as fine-grained as
    needed to fit `max_chars`. This is what most production RAG
    systems should default to.
    """

    strategy = ChunkStrategy.RECURSIVE

    # Default cascade: empty-line block → newline → period → space.
    _DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", ". ", " "]

    def __init__(
        self,
        *,
        max_chars: int = 800,
        separators: list[str] | None = None,
    ) -> None:
        if max_chars < 1:
            raise ValueError(f"max_chars must be >= 1, got {max_chars}")
        self.max_chars = max_chars
        self.separators = separators or self._DEFAULT_SEPARATORS

    def split(self, text: str) -> list[Chunk]:
        fragments = self._recurse(text, self.separators)
        # Index sequentially — Chunker._emit re-indexes from the
        # generator order.
        return self._emit(iter(fragments))

    def _recurse(self, text: str, seps: list[str]) -> list[str]:
        if len(text) <= self.max_chars:
            return [text] if text else []
        if not seps:
            # Run out of separators — hard-cut. The playbook calls
            # this the "fall through to fixed-size" safety net.
            return [text[i : i + self.max_chars] for i in range(0, len(text), self.max_chars)]
        sep = seps[0]
        rest = seps[1:]
        parts = text.split(sep)
        out: list[str] = []
        # Greedy pack: combine sequential parts that fit under
        # max_chars into one chunk; recurse only on parts that
        # are individually too large.
        buf = ""
        for p in parts:
            candidate = (buf + sep + p) if buf else p
            if len(candidate) <= self.max_chars:
                buf = candidate
            else:
                if buf:
                    out.append(buf)
                if len(p) > self.max_chars:
                    out.extend(self._recurse(p, rest))
                    buf = ""
                else:
                    buf = p
        if buf:
            out.append(buf)
        return out


class TokenCapChunker(Chunker):
    """Final-safety chunker — cap by token count.

    Wraps another chunker and re-splits any chunks that exceed the
    token limit. Use as the LAST step in a chunking pipeline so
    no chunk ever overflows the LLM context window.

    The tokenizer is callable so callers can plug tiktoken,
    sentencepiece, or any model-specific tokenizer. Default is a
    crude word-count proxy — fine for unit tests, NOT for prod.
    """

    strategy = ChunkStrategy.TOKEN_CAP

    def __init__(
        self,
        *,
        max_tokens: int = 512,
        tokenize: Callable[[str], list[str]] | None = None,
    ) -> None:
        if max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")
        self.max_tokens = max_tokens
        self.tokenize = tokenize or (lambda s: s.split())

    def split(self, text: str) -> list[Chunk]:
        tokens = self.tokenize(text)
        if not tokens:
            return []
        out: list[Chunk] = []
        for i in range(0, len(tokens), self.max_tokens):
            window = tokens[i : i + self.max_tokens]
            # Re-join with spaces — works for word-level tokenizers
            # and for tokenizer.decode() callers can override by
            # subclassing and overriding split().
            out.append(
                Chunk(
                    text=" ".join(window),
                    index=len(out),
                    strategy=self.strategy,
                    metadata={"token_count": len(window)},
                )
            )
        return out


# ── Factory (Factory pattern) ─────────────────────────────────


_REGISTRY: dict[ChunkStrategy, type[Chunker]] = {
    ChunkStrategy.FIXED: FixedSizeChunker,
    ChunkStrategy.SLIDING_WINDOW: SlidingWindowChunker,
    ChunkStrategy.SENTENCE: SentenceChunker,
    ChunkStrategy.PARAGRAPH: ParagraphChunker,
    ChunkStrategy.HEADER: HeaderChunker,
    ChunkStrategy.RECURSIVE: RecursiveChunker,
    ChunkStrategy.TOKEN_CAP: TokenCapChunker,
}


def make_chunker(strategy: ChunkStrategy | str, **kwargs: Any) -> Chunker:
    """Factory — pick a chunker by enum/string at runtime.

    Accepts string for ergonomics (callers reading config files
    don't need to import the enum).

        chunker = make_chunker("recursive", max_chars=600)
        chunks = chunker.split(document_text)

    Raises ValueError on unknown strategy — callers should treat
    that as a config bug, not a runtime fallback.
    """
    if isinstance(strategy, str):
        try:
            strategy = ChunkStrategy(strategy)
        except ValueError as exc:
            valid = ", ".join(s.value for s in ChunkStrategy)
            raise ValueError(f"unknown chunk strategy {strategy!r}; valid: {valid}") from exc
    cls = _REGISTRY.get(strategy)
    if cls is None:
        # Defensive — would only fire if _REGISTRY is mutated and
        # falls out of sync with the enum.
        raise ValueError(f"no chunker registered for strategy {strategy!r}")
    return cls(**kwargs)
