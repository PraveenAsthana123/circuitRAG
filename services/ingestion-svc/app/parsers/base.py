"""
Parser interface (Design Area 65 — Design-for-Change).

Every parser implements this protocol. Add a new format = add a class +
register it. Zero changes elsewhere.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedPage:
    """A single logical page (PDF page, DOCX section, HTML <article>)."""

    page_number: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Normalized representation returned by every parser.

    ``pages`` preserves structure so chunking can respect page boundaries
    and citations can point to page N.
    """

    title: str
    pages: list[ParsedPage]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


class DocumentParser(ABC):
    """Abstract parser. Concrete parsers subclass this."""

    #: File extensions this parser handles (lowercase, with dot).
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        """Parse raw bytes. Must not raise on malformed input that can be
        salvaged — prefer returning a best-effort ``ParsedDocument`` and
        flagging the issue in ``metadata['parse_warnings']``."""
