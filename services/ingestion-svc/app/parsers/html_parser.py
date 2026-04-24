"""HTML parser built on BeautifulSoup."""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from .base import DocumentParser, ParsedDocument, ParsedPage

log = logging.getLogger(__name__)


class HtmlParser(DocumentParser):
    extensions = (".html", ".htm")

    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        try:
            soup = BeautifulSoup(data, "lxml")
        except Exception as exc:
            log.warning("html_parse_failed filename=%s err=%s", filename, exc)
            return ParsedDocument(title=filename, pages=[], metadata={"parse_warnings": [str(exc)]})

        # Strip script/style — they have no textual value for RAG
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = (soup.title.string if soup.title and soup.title.string else filename).strip()

        # Split on <article>, <section>, or <h1> as logical pages
        sections = soup.find_all(["article", "section"]) or []
        if not sections:
            body = soup.body or soup
            text = body.get_text(separator="\n", strip=True)
            pages = [ParsedPage(page_number=1, text=text)]
        else:
            pages = [
                ParsedPage(
                    page_number=i,
                    text=s.get_text(separator="\n", strip=True),
                    metadata={"tag": s.name},
                )
                for i, s in enumerate(sections, start=1)
            ]

        return ParsedDocument(
            title=title,
            pages=pages,
            metadata={
                "source_filename": filename,
                "section_count": len(pages),
            },
        )
