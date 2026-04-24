"""PDF parser built on :mod:`pypdf`."""
from __future__ import annotations

import io
import logging

from pypdf import PdfReader

from .base import DocumentParser, ParsedDocument, ParsedPage

log = logging.getLogger(__name__)


class PdfParser(DocumentParser):
    extensions = (".pdf",)

    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        warnings: list[str] = []
        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as exc:
            log.warning("pdf_parse_reader_failed filename=%s err=%s", filename, exc)
            warnings.append(f"reader_init_failed: {exc}")
            return ParsedDocument(
                title=filename, pages=[], metadata={"parse_warnings": warnings}
            )

        title = (reader.metadata.title if reader.metadata else None) or filename
        pages: list[ParsedPage] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001
                log.warning("pdf_parse_page_failed filename=%s page=%d err=%s", filename, idx, exc)
                warnings.append(f"page_{idx}_extract_failed")
                text = ""
            pages.append(ParsedPage(page_number=idx, text=text))

        return ParsedDocument(
            title=str(title),
            pages=pages,
            metadata={
                "source_filename": filename,
                "page_count": len(pages),
                "parse_warnings": warnings,
            },
        )
