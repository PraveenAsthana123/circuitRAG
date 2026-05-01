"""
Token counting + budget helpers (§16.1 / §16.2 of the playbook).

Why this exists:
- Every LLM call has a hard token budget. Without a counter,
  callers ship payloads that get truncated server-side and the
  silent loss is invisible to operators.
- A pluggable Tokenizer protocol lets you swap word-count proxy
  (test/dev) → tiktoken (OpenAI) → sentencepiece (Llama family)
  without changing the caller.

DSA: This module is mostly the "Counter + sliding window" pattern
from §16.2 (cost tracking) plus a "greedy pack" for context-window
budgeting (§16.1 token-cap chunker uses the same idea).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

__all__ = ["Tokenizer", "WordTokenizer", "count_tokens", "pack_to_budget"]


class Tokenizer(Protocol):
    """Anything with a `.encode(text) -> list[int|str]` is a tokenizer.

    The actual return type doesn't matter for counting — only the
    length matters. Callers swap implementations via dependency
    injection.
    """

    def encode(self, text: str) -> Sequence[object]: ...


class WordTokenizer:
    """Whitespace word-counter. Cheap proxy for tests + dev.

    Production callers wrap tiktoken / sentencepiece behind the
    same protocol and swap this out via DI.
    """

    def encode(self, text: str) -> list[str]:
        return text.split()


def count_tokens(text: str, tokenizer: Tokenizer | None = None) -> int:
    """Return the token count for `text`.

    Defaults to :class:`WordTokenizer` (suitable for unit tests).
    Empty string → 0 (NEVER raises).
    """
    if not text:
        return 0
    tok = tokenizer or WordTokenizer()
    return len(tok.encode(text))


def pack_to_budget(
    fragments: Iterable[str],
    *,
    budget: int,
    tokenizer: Tokenizer | None = None,
    separator: str = "\n\n",
) -> tuple[list[str], int]:
    """Greedy-pack fragments into the token budget.

    Returns the (selected, total_tokens) tuple. Fragments are
    consumed in input order; the first one that would exceed the
    budget stops the pack — we do NOT skip it and try a smaller
    later fragment, because that re-orders context in ways the
    LLM may not expect.

    Edge cases:
    - budget < 1 raises ValueError (no silent empty-pack).
    - A single fragment LARGER than budget is excluded entirely
      (caller's job to chunk it before calling).
    - Empty fragments are skipped (don't count toward budget).
    """
    if budget < 1:
        raise ValueError(f"budget must be >= 1, got {budget}")

    tok = tokenizer or WordTokenizer()
    sep_tokens = count_tokens(separator, tok) if separator else 0

    selected: list[str] = []
    total = 0
    for frag in fragments:
        if not frag:
            continue
        frag_tokens = count_tokens(frag, tok)
        # First fragment doesn't pay separator cost.
        added = frag_tokens if not selected else frag_tokens + sep_tokens
        if total + added > budget:
            break
        selected.append(frag)
        total += added
    return selected, total
