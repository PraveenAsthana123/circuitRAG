"""Repo-local Langfuse import shim for offline inventory drills."""
from __future__ import annotations

__version__ = "compat-local"


class Langfuse:
    def __init__(self, *args, **kwargs) -> None:
        raise ImportError("Install langfuse for runtime tracing client calls")


__all__ = ["Langfuse"]
