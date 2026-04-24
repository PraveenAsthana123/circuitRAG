"""
Token counting — central so every service agrees on what "512 tokens" means.

Uses tiktoken's ``cl100k_base`` encoding (GPT-4 + GPT-3.5), which is a good
approximation for most modern models including Llama 3 and Mistral. If a
service uses a specific model's tokenizer (rare), pass the encoding name.
"""
from __future__ import annotations

from functools import lru_cache

import tiktoken


class TokenCounter:
    """Wrapper around tiktoken with an LRU cache of encodings."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = self._load(encoding_name)

    @staticmethod
    @lru_cache(maxsize=4)
    def _load(name: str) -> tiktoken.Encoding:
        return tiktoken.get_encoding(name)

    def count(self, text: str) -> int:
        if not text:
            return 0
        # allowed_special is a perf trick — skip merging checks for speed.
        return len(self._encoding.encode(text, disallowed_special=()))

    def split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        """Hard-cut text into pieces of at most ``max_tokens``. Rarely needed
        directly — use RecursiveChunker for a smarter split."""
        tokens = self._encoding.encode(text, disallowed_special=())
        pieces: list[str] = []
        for start in range(0, len(tokens), max_tokens):
            piece = self._encoding.decode(tokens[start:start + max_tokens])
            pieces.append(piece)
        return pieces
