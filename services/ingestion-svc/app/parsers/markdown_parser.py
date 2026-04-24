"""Markdown parser — renders to HTML then reuses HtmlParser. One code path
for the two formats instead of two subtly different ones."""
from __future__ import annotations

import markdown as md

from .base import DocumentParser, ParsedDocument
from .html_parser import HtmlParser


class MarkdownParser(DocumentParser):
    extensions = (".md", ".markdown")

    def __init__(self) -> None:
        self._html = HtmlParser()

    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        text = data.decode("utf-8", errors="replace")
        html = md.markdown(text, extensions=["tables", "fenced_code", "toc"])
        parsed = self._html.parse(html.encode(), filename=filename)
        parsed.metadata["source_format"] = "markdown"
        return parsed
