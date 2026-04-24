"""
Chunking (Design Area 23 — Ingestion, Area 34 — Retrieval Schema).

Why this is a whole package, not one function
---------------------------------------------
Chunking is the single highest-leverage decision in a RAG system. Different
document types benefit from different strategies:

* Legal contracts → recursive with clause-aware separators
* Code docs → AST-aware (split on function boundaries)
* Narrative text → semantic chunking (split on topic shifts)
* Slides → one chunk per slide

We package chunkers behind the :class:`Chunker` interface so downstream code
is strategy-agnostic, and governance can swap strategies per tenant.
"""
from .base import Chunk, Chunker
from .recursive import RecursiveChunker
from .token_counter import TokenCounter

__all__ = ["Chunk", "Chunker", "RecursiveChunker", "TokenCounter"]
