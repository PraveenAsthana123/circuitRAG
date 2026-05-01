"""
Tests for documind_core.query_rewriter — pre-retrieval query
normalization, expansion, and acronym detection.

Covers:
- RewriteResult is frozen (cache-key safety)
- Empty query returns empty result (no exception)
- Normalization: lowercase, whitespace collapse, curly quotes
- Expansions: word-boundary safe, case-insensitive, applied in order
- Multiple expansions can fire on one query
- Acronyms detected case-sensitively, deduplicated
- Acronyms detected on PRE-normalized text (otherwise lowercase
  killed the signal — that's the whole point of this layer)
- normalize=False keeps original casing
- Single-letter all-caps NOT flagged as acronym (too noisy)
- Expansions don't double-fire across runs
"""

from __future__ import annotations

import pytest

from documind_core.query_rewriter import QueryRewriter, RewriteResult


class TestRewriteResult:
    def test_frozen(self) -> None:
        r = RewriteResult(
            original="x",
            rewritten="y",
            expansions_applied=(),
            detected_acronyms=(),
        )
        with pytest.raises((AttributeError, Exception)):
            r.original = "z"  # type: ignore[misc]


class TestNormalize:
    def test_lowercase(self) -> None:
        r = QueryRewriter().rewrite("Hello WORLD")
        assert r.rewritten == "hello world"

    def test_whitespace_collapse(self) -> None:
        r = QueryRewriter().rewrite("  hello   \n  world  ")
        assert r.rewritten == "hello world"

    def test_curly_quotes_normalized(self) -> None:
        r = QueryRewriter().rewrite("It’s “great”")
        assert "'" in r.rewritten or "’" not in r.rewritten
        assert '"' in r.rewritten or "“" not in r.rewritten

    def test_normalize_false_keeps_case(self) -> None:
        r = QueryRewriter(normalize=False).rewrite("Hello WORLD")
        assert r.rewritten == "Hello WORLD"


class TestExpansions:
    def test_simple_expansion(self) -> None:
        r = QueryRewriter(expansions={"ny": "new york"}).rewrite("policies in NY")
        assert "new york" in r.rewritten
        assert "ny" in r.expansions_applied

    def test_word_boundary_safe(self) -> None:
        # Must NOT expand "ny" inside "any" or "many".
        r = QueryRewriter(expansions={"ny": "new york"}).rewrite("many anyone")
        assert r.rewritten == "many anyone"
        assert r.expansions_applied == ()

    def test_multiple_expansions_one_query(self) -> None:
        r = QueryRewriter(expansions={"ny": "new york", "ca": "california"}).rewrite("offices in NY and CA")
        assert "new york" in r.rewritten
        assert "california" in r.rewritten
        assert set(r.expansions_applied) == {"ny", "ca"}

    def test_no_match_no_expansion_recorded(self) -> None:
        r = QueryRewriter(expansions={"ny": "new york"}).rewrite("hello world")
        assert r.expansions_applied == ()

    def test_case_insensitive_match(self) -> None:
        # All of "ny", "NY", "Ny" should fire.
        for q in ("ny", "NY", "Ny"):
            r = QueryRewriter(expansions={"ny": "new york"}).rewrite(f"in {q}")
            assert "new york" in r.rewritten


class TestAcronymDetection:
    def test_acronym_detected(self) -> None:
        r = QueryRewriter().rewrite("Find docs about NLP and MCP")
        assert "NLP" in r.detected_acronyms
        assert "MCP" in r.detected_acronyms

    def test_acronyms_deduplicated(self) -> None:
        r = QueryRewriter().rewrite("RAG vs RAG")
        # Only one "RAG" in detected_acronyms.
        assert r.detected_acronyms.count("RAG") == 1

    def test_lowercase_text_no_acronyms(self) -> None:
        r = QueryRewriter().rewrite("nlp mcp rag")
        assert r.detected_acronyms == ()

    def test_single_letter_not_acronym(self) -> None:
        # "I want X" — single letters create noise. Skip.
        r = QueryRewriter().rewrite("I want X")
        assert "I" not in r.detected_acronyms
        assert "X" not in r.detected_acronyms

    def test_word_with_caps_inside_not_acronym(self) -> None:
        # "JavaScript" has caps but is NOT an acronym.
        r = QueryRewriter().rewrite("JavaScript runtime")
        assert "JavaScript" not in r.detected_acronyms

    def test_acronym_detected_before_normalization(self) -> None:
        # Critical: if normalize=True, the rewritten text is
        # lowercase. But the acronym detection MUST run on the
        # original — otherwise normalize destroys the signal we
        # care about.
        r = QueryRewriter(normalize=True).rewrite("Find NLP docs")
        assert "NLP" in r.detected_acronyms
        assert "nlp" in r.rewritten  # rewritten IS lowercase


class TestEmptyAndEdge:
    def test_empty_query(self) -> None:
        r = QueryRewriter().rewrite("")
        assert r.original == ""
        assert r.rewritten == ""
        assert r.expansions_applied == ()
        assert r.detected_acronyms == ()
