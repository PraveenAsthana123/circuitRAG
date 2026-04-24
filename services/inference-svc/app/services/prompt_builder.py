"""
Prompt construction + versioning (Design Area 32 — Prompt Contract).

Prompts are versioned artifacts: each template has a stable name + version.
Every LLM response records which version generated it, so quality regressions
are traceable to specific prompt changes.

In production, templates live in the ``governance.prompts`` table and are
fetched at startup + periodically refreshed. For the demo we inline them so
the service runs standalone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    user_template: str
    max_context_tokens: int = 4000


PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    "rag_answer_v1": PromptTemplate(
        name="rag_answer",
        version="v1",
        system=(
            "You are a careful document-intelligence assistant. "
            "Answer the user's question using ONLY the provided context. "
            "If the context does not contain enough information, say: "
            '"I don\'t have enough information in the provided documents." '
            "Always cite sources inline using the format [Source: <filename>, Page N] "
            "matching one of the chunks. Do NOT invent citations."
        ),
        user_template=(
            "Context:\n"
            "{context}\n\n"
            "Question: {query}\n\n"
            "Answer:"
        ),
    ),
    "summarize_v1": PromptTemplate(
        name="summarize",
        version="v1",
        system=(
            "You are a precise technical summarizer. Produce a bulleted summary "
            "of the provided text, preserving page numbers as citations."
        ),
        user_template="Summarize the following:\n\n{context}\n\nBulleted summary:",
    ),
}


class PromptBuilder:
    """Construct the final prompt + citation map for a given template."""

    def __init__(self, templates: dict[str, PromptTemplate] | None = None) -> None:
        self._templates = templates or PROMPT_TEMPLATES

    def get(self, name: str) -> PromptTemplate:
        try:
            return self._templates[name]
        except KeyError as exc:
            raise KeyError(f"Unknown prompt template '{name}'") from exc

    def build(
        self,
        *,
        template_name: str,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> tuple[str, str, list[dict[str, Any]]]:
        """
        Return ``(system_prompt, user_prompt, citation_map)``.

        ``citation_map`` is the list of chunks we included in context, with
        their citation label assigned (``[Source: ..., Page N]``). The
        inference-svc uses it to validate that the LLM's citations resolve
        to real chunks.
        """
        tmpl = self.get(template_name)
        citation_map: list[dict[str, Any]] = []
        context_lines: list[str] = []
        for c in chunks:
            filename = (c.get("metadata") or {}).get("source_filename") or str(c.get("document_id"))
            label = f"[Source: {filename}, Page {c.get('page_number', 0)}]"
            snippet = c.get("text", "").strip()
            context_lines.append(f"{label}\n{snippet}")
            citation_map.append(
                {
                    "chunk_id": c["chunk_id"],
                    "document_id": c["document_id"],
                    "page_number": c.get("page_number", 0),
                    "snippet": snippet[:240],
                    "label": label,
                }
            )

        context = "\n\n".join(context_lines)
        user = tmpl.user_template.format(context=context, query=query)
        return tmpl.system, user, citation_map
