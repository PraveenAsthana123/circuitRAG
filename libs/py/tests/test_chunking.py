"""
Tests for documind_core.chunking — Strategy + Factory pattern, 7
deterministic chunkers.

Covers:
- Chunk dataclass + frozen invariant
- Each chunker's happy path + edge cases (empty, single-segment,
  whitespace-only, oversized fragment)
- Factory accepts enum + string + raises on unknown
- chunker_version stamped on every chunk (regression-locks the
  cache-key contract from §1.4 of the playbook)
- HeaderChunker negative: no-headings text falls through to
  paragraph chunking with header_path="(none)" (NEGATIVE)
- TokenCapChunker re-splits oversized text (last-resort safety)
- RecursiveChunker greedy-pack: doesn't fragment when not needed
"""

from __future__ import annotations

import pytest

from documind_core.chunking import (
    CHUNKER_VERSION,
    Chunk,
    ChunkStrategy,
    FixedSizeChunker,
    HeaderChunker,
    ParagraphChunker,
    RecursiveChunker,
    SentenceChunker,
    SlidingWindowChunker,
    TokenCapChunker,
    make_chunker,
)

# ── Chunk dataclass ───────────────────────────────────────────


class TestChunk:
    def test_frozen(self) -> None:
        # Frozen so chunks can be cache keys without aliasing risk.
        c = Chunk(text="x", index=0, strategy=ChunkStrategy.FIXED)
        with pytest.raises((AttributeError, Exception)):  # frozen dataclass
            c.text = "y"  # type: ignore[misc]

    def test_default_version_stamped(self) -> None:
        c = Chunk(text="x", index=0, strategy=ChunkStrategy.FIXED)
        assert c.chunker_version == CHUNKER_VERSION

    def test_len(self) -> None:
        assert len(Chunk(text="hello", index=0, strategy=ChunkStrategy.FIXED)) == 5


# ── FixedSizeChunker ──────────────────────────────────────────


class TestFixed:
    def test_simple_split(self) -> None:
        chunks = FixedSizeChunker(size=5).split("aaaaabbbbbccccc")
        assert [c.text for c in chunks] == ["aaaaa", "bbbbb", "ccccc"]
        assert all(c.strategy == ChunkStrategy.FIXED for c in chunks)

    def test_empty_text(self) -> None:
        assert FixedSizeChunker(size=10).split("") == []

    def test_size_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="size"):
            FixedSizeChunker(size=0)

    def test_whitespace_only_chunks_dropped(self) -> None:
        # Trailing whitespace would create empty chunks; _emit drops them.
        chunks = FixedSizeChunker(size=3).split("ab   ")
        assert all(c.text.strip() for c in chunks)


# ── SlidingWindowChunker ──────────────────────────────────────


class TestSlidingWindow:
    def test_overlap_repeats_text(self) -> None:
        chunks = SlidingWindowChunker(size=5, overlap=2).split("0123456789")
        # step = 3, so windows start at 0, 3, 6, 9
        assert chunks[0].text == "01234"
        assert chunks[1].text == "34567"
        assert chunks[2].text == "6789"

    def test_overlap_geq_size_rejected(self) -> None:
        # Without this guard, overlap=size means infinite loop.
        with pytest.raises(ValueError, match="overlap"):
            SlidingWindowChunker(size=5, overlap=5)

    def test_empty_text(self) -> None:
        assert SlidingWindowChunker(size=5, overlap=1).split("") == []


# ── SentenceChunker ───────────────────────────────────────────


class TestSentence:
    def test_basic_split(self) -> None:
        text = "Hello world. This is fine. Another one!"
        chunks = SentenceChunker().split(text)
        assert len(chunks) == 3

    def test_max_chars_caps_long_sentence(self) -> None:
        # NEGATIVE-shaped: one giant sentence MUST get hard-split,
        # otherwise downstream embedder gets a token-overflow blow-up.
        long_sentence = "A" * 1000
        chunks = SentenceChunker(max_chars=200).split(long_sentence)
        assert all(len(c) <= 200 for c in chunks)
        assert len(chunks) == 5

    def test_empty_text(self) -> None:
        assert SentenceChunker().split("") == []


# ── ParagraphChunker ──────────────────────────────────────────


class TestParagraph:
    def test_blank_line_separated(self) -> None:
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = ParagraphChunker().split(text)
        assert [c.text for c in chunks] == ["Para one.", "Para two.", "Para three."]

    def test_single_paragraph(self) -> None:
        chunks = ParagraphChunker().split("just one block")
        assert [c.text for c in chunks] == ["just one block"]

    def test_empty_strings_filtered(self) -> None:
        # Multiple consecutive blank lines must NOT produce empty chunks.
        chunks = ParagraphChunker().split("a\n\n\n\nb")
        assert [c.text for c in chunks] == ["a", "b"]


# ── HeaderChunker ─────────────────────────────────────────────


class TestHeader:
    def test_simple_h1(self) -> None:
        text = "# Title\nbody one\n# Other\nbody two"
        chunks = HeaderChunker().split(text)
        assert [c.metadata["header_path"] for c in chunks] == ["Title", "Other"]

    def test_nested_headers_compose_path(self) -> None:
        # The header_path is the load-bearing value-add.
        text = "# Top\nintro\n## Sub\ndetail\n### Subsub\nfine print"
        chunks = HeaderChunker().split(text)
        assert chunks[0].metadata["header_path"] == "Top"
        assert chunks[1].metadata["header_path"] == "Top > Sub"
        assert chunks[2].metadata["header_path"] == "Top > Sub > Subsub"

    def test_no_headers_falls_back_to_paragraph(self) -> None:
        # NEGATIVE: when the doc has no headings, the chunker MUST
        # NOT silently produce zero output. It degrades to paragraph
        # with a sentinel header_path so callers can detect.
        text = "no headings here\n\nstill no headings"
        chunks = HeaderChunker().split(text)
        assert all(c.metadata["header_path"] == "(none)" for c in chunks)
        assert len(chunks) == 2

    def test_skips_header_with_empty_body(self) -> None:
        # Headings with no body should NOT produce empty chunks.
        text = "# Empty\n# Real\nactual content"
        chunks = HeaderChunker().split(text)
        assert len(chunks) == 1
        assert chunks[0].text == "actual content"


# ── RecursiveChunker ──────────────────────────────────────────


class TestRecursive:
    def test_under_limit_returns_single_chunk(self) -> None:
        # Greedy-pack: no need to split if it fits.
        chunks = RecursiveChunker(max_chars=1000).split("short text")
        assert [c.text for c in chunks] == ["short text"]

    def test_splits_on_first_separator(self) -> None:
        # Two paragraphs, max_chars too small to fit both.
        text = "para one is here\n\npara two is here"
        chunks = RecursiveChunker(max_chars=20).split(text)
        # Should split on \n\n first (default separator order).
        assert len(chunks) == 2

    def test_falls_through_separator_cascade(self) -> None:
        # No paragraph breaks, no newlines — must fall through to
        # period split, then space, then hard cut. Long paragraph
        # of sentences.
        text = ". ".join(["sentence " + str(i) for i in range(20)])
        chunks = RecursiveChunker(max_chars=50).split(text)
        # Every chunk under cap; total content preserved.
        assert all(len(c) <= 50 for c in chunks)
        # No information lost (modulo separators).
        joined = ". ".join(c.text for c in chunks)
        # Roughly preserves the original (allowing for dropped " ").
        assert "sentence 0" in joined and "sentence 19" in joined

    def test_max_chars_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_chars"):
            RecursiveChunker(max_chars=0)

    def test_oversized_atomic_unit_hard_cut(self) -> None:
        # NEGATIVE safety net: a single 10K-char "word" with no
        # separators must STILL be split at max_chars.
        text = "x" * 1000
        chunks = RecursiveChunker(max_chars=200).split(text)
        assert all(len(c) <= 200 for c in chunks)
        assert sum(len(c) for c in chunks) == 1000


# ── TokenCapChunker ───────────────────────────────────────────


class TestTokenCap:
    def test_caps_at_max_tokens(self) -> None:
        text = " ".join(f"word{i}" for i in range(100))
        chunks = TokenCapChunker(max_tokens=20).split(text)
        # Default tokenize = whitespace split → exactly 5 chunks of 20.
        assert len(chunks) == 5
        for c in chunks:
            assert c.metadata["token_count"] <= 20

    def test_custom_tokenizer(self) -> None:
        # Plug a model-specific tokenizer.
        chunks = TokenCapChunker(max_tokens=2, tokenize=list).split("abcd")
        # list("abcd") → ["a","b","c","d"]; max 2 → 2 chunks.
        assert len(chunks) == 2

    def test_max_tokens_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens"):
            TokenCapChunker(max_tokens=0)

    def test_empty_text(self) -> None:
        assert TokenCapChunker(max_tokens=10).split("") == []


# ── Factory ───────────────────────────────────────────────────


class TestFactory:
    def test_enum(self) -> None:
        c = make_chunker(ChunkStrategy.RECURSIVE, max_chars=400)
        assert isinstance(c, RecursiveChunker)
        assert c.max_chars == 400

    def test_string(self) -> None:
        # Config-file ergonomics — callers shouldn't have to import enum.
        c = make_chunker("paragraph")
        assert isinstance(c, ParagraphChunker)

    def test_unknown_strategy_raises(self) -> None:
        # NEGATIVE: silent fallback to a default chunker would mask
        # config bugs. Always raise.
        with pytest.raises(ValueError, match="unknown chunk strategy"):
            make_chunker("does-not-exist")

    def test_kwargs_forwarded(self) -> None:
        c = make_chunker("sliding_window", size=100, overlap=10)
        assert c.size == 100  # type: ignore[attr-defined]
        assert c.overlap == 10  # type: ignore[attr-defined]


# ── chunker_version stamped on every Chunk (cache-key contract) ──


class TestChunkerVersion:
    def test_every_strategy_stamps_version(self) -> None:
        # Per playbook §1.4: chunk cache keys MUST include the
        # chunker_version. If a strategy ever omits it, caches
        # silently serve stale chunks after a strategy change.
        sample = "para one\n\npara two"
        for strategy in ChunkStrategy:
            chunker = make_chunker(strategy)
            chunks = chunker.split(sample)
            # Some strategies produce zero chunks for short text
            # (e.g. token-cap with max_tokens=512 + 4-token text
            # → 1 chunk; sliding_window default size=500 → 1 chunk).
            for c in chunks:
                assert c.chunker_version == CHUNKER_VERSION, f"strategy {strategy.value} did not stamp chunker_version"
                assert c.strategy == strategy
