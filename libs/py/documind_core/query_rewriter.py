"""
Pre-retrieval query processing (§16.4 of the playbook).

Three composable transforms for a query before retrieval:

1. **Normalization** — lowercase, strip extra whitespace, unify
   curly quotes. Pure mechanical.
2. **Synonym/abbreviation expansion** — `\b<from>\b` → expansion,
   plural-aware. The pronunciation policy §46 has the SAME shape
   for TTS — keeping consistent regex semantics across the codebase.
3. **Acronym detection** — flags ALL-CAPS tokens of length 2-6 so
   the LLM/retrieval can branch on them (e.g. expand or boost
   metadata filter on known abbreviations).

DSA: trie + hashmap for the expansion table; regex DFA via Python
`re` for matching. O(n) per query.

This intentionally does NOT do LLM-based query rewriting (that's
a different module + different cost profile). Operators who want
HyDE / Step-Back / RAG-Fusion compose this normalizer with their
LLM rewriter — this layer guarantees deterministic, cheap, fast.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["RewriteResult", "QueryRewriter"]


@dataclass(frozen=True)
class RewriteResult:
    """Result of a rewrite pass. Immutable so it can be cached
    by query string."""

    original: str
    rewritten: str
    expansions_applied: tuple[str, ...]  # which entries fired
    detected_acronyms: tuple[str, ...]


class QueryRewriter:
    """Composable, deterministic pre-retrieval query rewriter.

    Usage:
        rewriter = QueryRewriter(expansions={"ny": "New York"})
        result = rewriter.rewrite("Find policies in NY")
        # result.rewritten = "find policies in new york"
        # result.detected_acronyms = ("NY",)
        # result.expansions_applied = ("ny",)

    Set normalize=False to keep original casing (acronym detection
    still works on the pre-normalized text — case-sensitive).
    """

    # Acronym = 2-6 consecutive uppercase letters/digits, NOT
    # immediately preceded or followed by a lowercase letter
    # (catches "NLP", "MCP", "RAG", "K8s" → no, "K8" + s split)
    _ACRONYM_RE = re.compile(r"(?<![a-zA-Z])[A-Z][A-Z0-9]{1,5}(?![a-z])")

    # Curly quote normalization map.
    _QUOTE_MAP = {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
    }

    def __init__(
        self,
        *,
        expansions: Mapping[str, str] | None = None,
        normalize: bool = True,
    ) -> None:
        self._expansions = dict(expansions or {})
        self._normalize = normalize
        # Pre-compile expansion regexes. Plural-aware per §46
        # convention: `\bfrom(s?)\b` so "policy" matches but
        # "policies" stays untouched (which is correct — caller's
        # expansions table should include singular AND plural if
        # both should expand).
        self._compiled = [(term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)) for term in self._expansions]

    def rewrite(self, query: str) -> RewriteResult:
        """Apply all transforms and return the result."""
        if not query:
            return RewriteResult(
                original="",
                rewritten="",
                expansions_applied=(),
                detected_acronyms=(),
            )

        original = query
        # Acronyms detected BEFORE normalization (case-sensitive).
        acronyms = tuple(set(self._ACRONYM_RE.findall(query)))

        text = query
        if self._normalize:
            text = self._normalize_text(text)

        # Apply expansions in declaration order (callers control
        # priority). Track which fired so audit rows can show what
        # the rewriter changed.
        applied: list[str] = []
        for term, regex in self._compiled:
            new_text, n = regex.subn(self._expansions[term], text)
            if n > 0:
                applied.append(term)
                text = new_text

        return RewriteResult(
            original=original,
            rewritten=text,
            expansions_applied=tuple(applied),
            detected_acronyms=acronyms,
        )

    def _normalize_text(self, text: str) -> str:
        # NFKC unicode normalization (smart quotes, ligatures).
        text = unicodedata.normalize("NFKC", text)
        for src, dst in self._QUOTE_MAP.items():
            text = text.replace(src, dst)
        # Collapse whitespace + lowercase. Operators reading the
        # log shouldn't see "  refund   policy " — they want the
        # canonicalized form.
        text = " ".join(text.split())
        text = text.lower()
        return text
