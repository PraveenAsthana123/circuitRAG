"""Plain-text parser (.txt). No structure beyond paragraphs."""
from __future__ import annotations

from .base import DocumentParser, ParsedDocument, ParsedPage


class TextParser(DocumentParser):
    extensions = (".txt",)

    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        text = data.decode("utf-8", errors="replace")
        # Treat each double-newline-separated block as a page so downstream
        # chunking has natural boundaries.
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        pages = (
            [ParsedPage(page_number=i, text=b) for i, b in enumerate(blocks, start=1)]
            or [ParsedPage(page_number=1, text=text)]
        )
        return ParsedDocument(
            title=filename,
            pages=pages,
            metadata={"source_filename": filename, "block_count": len(pages)},
        )
