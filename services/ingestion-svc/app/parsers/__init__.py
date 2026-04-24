"""
Document parsers (Design Area 23 — Knowledge Ingestion, Design Area 65 —
Design-for-Change).

All parsers implement the :class:`DocumentParser` interface. To add a new
format, write a class and register it in :data:`PARSERS`; nothing else
needs to change — the ``ParserRegistry`` picks it up by extension.

Learning notes
--------------
* **Why class-per-format?** Each format has format-specific state (PDF
  fonts, DOCX styles). Shoving all formats into one function produces
  unmaintainable if/else chains. One class per format keeps each one
  independently testable and swappable.
* **Why return ``ParsedDocument`` instead of raw text?** We preserve
  structure (pages, headings, tables) so downstream chunking can respect
  boundaries and citations can point to exact pages.
"""
from __future__ import annotations

from .base import DocumentParser, ParsedDocument, ParsedPage
from .pdf_parser import PdfParser
from .docx_parser import DocxParser
from .html_parser import HtmlParser
from .text_parser import TextParser
from .markdown_parser import MarkdownParser
from .registry import ParserRegistry

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "ParsedPage",
    "PdfParser",
    "DocxParser",
    "HtmlParser",
    "TextParser",
    "MarkdownParser",
    "ParserRegistry",
]
