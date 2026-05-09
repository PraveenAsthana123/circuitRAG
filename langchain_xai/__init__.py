"""Repo-local no-call compatibility surface for xAI LangChain clients."""
from __future__ import annotations

import os

__version__ = "compat-local"


class ChatXAI:
    """Minimal import-time surface for offline probes.

    Real xAI calls still require the upstream `langchain-xai` package and
    `XAI_API_KEY`. This class exists so inventory drills and dashboards can
    report the missing key honestly without importing a broken optional stack.
    """

    def __init__(self, *args, **kwargs) -> None:
        if not os.environ.get("XAI_API_KEY"):
            raise ValueError("XAI_API_KEY is required before ChatXAI can be used")
        raise ImportError("Install langchain-xai for runtime ChatXAI calls")


__all__ = ["ChatXAI"]
