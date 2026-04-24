"""Parser registry — picks the right parser by file extension."""
from __future__ import annotations

import os

from documind_core.exceptions import ValidationError

from .base import DocumentParser
from .docx_parser import DocxParser
from .html_parser import HtmlParser
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .text_parser import TextParser


class ParserRegistry:
    """
    Maps file extensions to parser instances. Instances are cached — parsers
    have no per-request state, so one instance per registry is fine.
    """

    def __init__(self, parsers: list[DocumentParser] | None = None) -> None:
        self._by_ext: dict[str, DocumentParser] = {}
        for p in parsers or self._default_parsers():
            for ext in p.extensions:
                self._by_ext[ext.lower()] = p

    @staticmethod
    def _default_parsers() -> list[DocumentParser]:
        return [PdfParser(), DocxParser(), HtmlParser(), TextParser(), MarkdownParser()]

    def supports(self, filename: str) -> bool:
        return self._extension(filename) in self._by_ext

    def get(self, filename: str) -> DocumentParser:
        ext = self._extension(filename)
        if ext not in self._by_ext:
            raise ValidationError(
                f"Unsupported file type '{ext}'",
                details={"filename": filename, "supported": sorted(self._by_ext)},
            )
        return self._by_ext[ext]

    @staticmethod
    def _extension(filename: str) -> str:
        return os.path.splitext(filename)[1].lower()
