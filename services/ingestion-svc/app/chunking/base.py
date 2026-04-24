"""Chunker interface + Chunk domain model."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.parsers import ParsedDocument


@dataclass
class Chunk:
    """A unit of text ready for embedding + indexing."""

    #: Stable content hash — used as idempotency key (same text → same hash →
    #: skip re-embedding). SHA-256 over normalized text.
    content_hash: str

    #: 0-based index within the parent document.
    index: int

    #: The text itself.
    text: str

    #: Token count (model-specific — uses the shared TokenCounter).
    token_count: int

    #: Page number in the source document (for citations).
    page_number: int

    #: Free-form metadata: headings, section path, language, etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def hash_content(text: str) -> str:
        """Deterministic content hash. Whitespace-normalized."""
        normalized = " ".join(text.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        """Split a parsed document into chunks."""
