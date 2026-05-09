"""Repo-local compatibility surface for LangChain Ollama integrations.

The installed `langchain-ollama` wheel in some operator environments can
require a newer `langchain-core` than the rest of this repo is pinned to.
This module keeps read-only inventory and fallback code importable without
performing any network call or model load.
"""
from __future__ import annotations

__version__ = "compat-local"

try:  # Prefer the community implementations when present.
    from langchain_community.chat_models.ollama import ChatOllama as ChatOllama
except Exception:  # pragma: no cover - fallback is environment-dependent
    class ChatOllama:  # type: ignore[no-redef]
        """Placeholder that fails only when an operator tries to instantiate it."""

        def __init__(self, *args, **kwargs) -> None:
            raise ImportError(
                "ChatOllama requires langchain_community.chat_models.ollama "
                "or a compatible langchain-ollama install"
            )

try:
    from langchain_community.embeddings.ollama import OllamaEmbeddings as OllamaEmbeddings
except Exception:  # pragma: no cover - fallback is environment-dependent
    class OllamaEmbeddings:  # type: ignore[no-redef]
        """Placeholder that fails only when an operator tries to instantiate it."""

        def __init__(self, *args, **kwargs) -> None:
            raise ImportError(
                "OllamaEmbeddings requires langchain_community.embeddings.ollama "
                "or a compatible langchain-ollama install"
            )


__all__ = ["ChatOllama", "OllamaEmbeddings"]
