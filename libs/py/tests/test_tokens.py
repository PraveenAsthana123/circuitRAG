"""
Tests for documind_core.tokens — token counting + budget packing.

Covers:
- WordTokenizer.encode (whitespace split)
- count_tokens with default tokenizer
- count_tokens with custom tokenizer
- Empty string returns 0 (no exception)
- pack_to_budget basic happy path
- pack_to_budget stops at budget (greedy, no skip-and-try-later)
- pack_to_budget separator tokens counted between fragments
- pack_to_budget budget < 1 raises (catches config bug)
- pack_to_budget single oversized fragment excluded
- pack_to_budget empty fragments skipped
"""

from __future__ import annotations

import pytest

from documind_core.tokens import (
    WordTokenizer,
    count_tokens,
    pack_to_budget,
)


class TestWordTokenizer:
    def test_split_on_whitespace(self) -> None:
        assert WordTokenizer().encode("the quick brown fox") == ["the", "quick", "brown", "fox"]

    def test_empty(self) -> None:
        assert WordTokenizer().encode("") == []


class TestCountTokens:
    def test_default(self) -> None:
        assert count_tokens("hello world") == 2

    def test_empty(self) -> None:
        # NEVER raises on empty.
        assert count_tokens("") == 0

    def test_custom_tokenizer(self) -> None:
        class CharTok:
            def encode(self, t: str) -> list[str]:
                return list(t)

        assert count_tokens("abc", CharTok()) == 3


class TestPackToBudget:
    def test_basic_pack(self) -> None:
        # Each fragment is 2 tokens, separator is 0 (we set that).
        # Budget 5 → only 2 fragments fit (4 tokens), 3rd would
        # bring us to 6.
        selected, total = pack_to_budget(
            ["a b", "c d", "e f"],
            budget=5,
            separator="",
        )
        assert len(selected) == 2
        assert total == 4

    def test_separator_counted_between_fragments(self) -> None:
        # Default separator "\n\n" = 1 token by word-count proxy
        # (it's one whitespace-separated chunk: "\n\n" with no spaces
        # would be 1 token... actually .split() returns []).
        # Let's use an explicit separator to be precise.
        selected, _ = pack_to_budget(
            ["a b", "c d", "e f"],
            budget=7,
            separator=" SEP ",  # 1 token
        )
        # First: 2 tokens. Second: 2 + 1 sep = 3, total 5. Third:
        # 2 + 1 sep = 3, total 8 > 7 → exclude.
        assert len(selected) == 2

    def test_first_fragment_no_separator_cost(self) -> None:
        # Even with separator, the FIRST fragment doesn't pay for it.
        selected, total = pack_to_budget(
            ["a b c"],
            budget=3,
            separator=" SEP ",
        )
        assert len(selected) == 1
        assert total == 3

    def test_budget_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="budget"):
            pack_to_budget(["a"], budget=0)

    def test_oversized_fragment_excluded(self) -> None:
        # A single fragment larger than the budget is excluded —
        # we don't half-pack it. Caller must chunk first.
        selected, _ = pack_to_budget(
            ["a b c d e f"],
            budget=3,
            separator="",
        )
        assert selected == []

    def test_empty_fragments_skipped(self) -> None:
        selected, total = pack_to_budget(
            ["", "a b", "", "c"],
            budget=10,
            separator="",
        )
        assert selected == ["a b", "c"]
        assert total == 3

    def test_greedy_stops_at_first_overflow(self) -> None:
        # Even if a LATER fragment would fit, we stop at the first
        # overflow. This preserves context order for the LLM.
        selected, _ = pack_to_budget(
            ["a b", "c d e f g h", "tiny"],
            budget=5,
            separator="",
        )
        # First fits (2/5). Second is 6 tokens > 5 remaining → break.
        # Third is NOT considered.
        assert selected == ["a b"]
