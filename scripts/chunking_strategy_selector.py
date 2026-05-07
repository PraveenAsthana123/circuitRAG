"""Chunking strategy selector — Stage-1 adapter (per CLAUDE.md §56).

Realizes the operator-supplied "Chunking Decision Engine" spec:
  Input file → detect data type → classify use case → estimate cost
  → SELECT chunking strategy → apply metadata → quality gate → index.

This module is the SELECTOR — it takes (file_type, use_case,
cost_priority, accuracy_priority) and returns a structured
ChunkingStrategy spec matching the operator's recommended JSON
schema. The downstream chunker (services/ingestion-svc/app/chunking)
applies the strategy.

WHY THIS SHAPE (Stage-1, NOT Stage-3 chunker rewrite):
  Modifying the existing Chunker is touching tested production code
  (rate-limited at 10/window/tenant). Per §56 6-gate, we ship the
  selector first, drill it, then Stage-2 wires it into the saga
  (one-line: `strategy = selector.choose(file_type=..., use_case=...)`).

OPERATOR SPEC MAPPING:
  - 23 data types (TXT, PDF, DOCX, PPT, HTML, Markdown, CSV, Excel,
    JSON, XML, Logs, Code, SQL, API Docs, Emails, Tickets, Chat,
    Images, Audio, Video, IoT, Geospatial, Graph)
  - Per-type strategy + chunk_size + overlap + metadata fields +
    quality checks (matching the 21-row chunking-by-data-type table)
  - Cost/accuracy modulation (the 5-rule pseudocode)
  - Output JSON schema matches operator's recommended output

OPERATOR OPT-IN:
    CHUNKING_STRATEGY_SELECTOR_ENABLED=1

COMPOSES WITH (per §49):
    services/ingestion-svc/app/chunking — the actual chunker (Stage-2 wiring site)
    services/ingestion-svc/app/services/ingestion_service.py — saga caller
    services/ingestion-svc/app/services/pii_hook.py — runs BEFORE chunker
    docs/architecture/chunking-decision-engine-2026-05-04.md — design doc
    §38 — decision audit (selector choice persisted on every ingest)
    §39 — RAG architecture (chunking-strategy is § rule)
    §43 — drill discipline
    §52 — brutal tool review (40-row when wired into saga)
    §56 — Stage-1 6-gate adoption
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)

CHUNKING_STRATEGY_SELECTOR_ENABLED = os.getenv(
    "CHUNKING_STRATEGY_SELECTOR_ENABLED", "",
).strip() == "1"


class ChunkingSelectorDisabled(RuntimeError):
    """Raised when choose() is called but the env flag is unset."""


@dataclass
class ChunkingStrategy:
    """Structured spec the downstream chunker applies. Schema matches
    the operator's recommended output (per the latest chunking spec)."""
    strategy_name: str
    file_type: str
    use_case: str
    chunk_size_tokens: int
    overlap_percent: int
    metadata_fields: list[str] = field(default_factory=list)
    quality_checks: list[str] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ───────────────────────────────────────────────────────────────────
# 23-row strategy table (operator-supplied)
# ───────────────────────────────────────────────────────────────────
# Each entry encodes the 4-column row: best chunking + chunk size +
# overlap + metadata fields, derived from the operator's tables.
_STRATEGY_TABLE: dict[str, dict[str, Any]] = {
    "txt":      {"name": "recursive_paragraph_sentence", "size": 500, "overlap": 15,
                 "metadata": ["source_id", "chunk_id", "section", "token_count"]},
    "pdf":      {"name": "layout_section_page_aware",   "size": 600, "overlap": 20,
                 "metadata": ["page_number", "section", "bbox", "source_file"]},
    "docx":     {"name": "heading_section_table_aware", "size": 600, "overlap": 15,
                 "metadata": ["heading", "subheading", "table_id", "image_ref"]},
    "ppt":      {"name": "slide_notes_image_caption",   "size": 1, "overlap": 0,
                 "metadata": ["slide_number", "title", "speaker_notes", "image_refs"]},
    "html":     {"name": "dom_aware_main_body",         "size": 500, "overlap": 12,
                 "metadata": ["url", "h1", "h2", "dom_path", "canonical_url"]},
    "md":       {"name": "heading_codeblock_aware",     "size": 500, "overlap": 15,
                 "metadata": ["heading_path", "code_block_flag", "section_id"]},
    "csv":      {"name": "schema_plus_row_group",       "size": 500, "overlap": 0,
                 "metadata": ["file", "row_start", "row_end", "columns", "schema_hash"]},
    "xlsx":     {"name": "sheet_table_range_aware",     "size": 500, "overlap": 0,
                 "metadata": ["sheet_name", "cell_range", "table_name", "schema"]},
    "json":     {"name": "tree_path_object_aware",      "size": 1, "overlap": 0,
                 "metadata": ["json_path", "object_id", "parent_path", "entity_type"]},
    "xml":      {"name": "tag_entity_xpath",            "size": 1, "overlap": 0,
                 "metadata": ["xml_path", "tag_name", "entity_id", "namespace"]},
    "logs":     {"name": "time_window_request_id",      "size": 500, "overlap": 5,
                 "metadata": ["timestamp", "service", "request_id", "severity"]},
    "code":     {"name": "function_class_ast",          "size": 1, "overlap": 0,
                 "metadata": ["file_path", "class", "function", "imports", "language"]},
    "sql":      {"name": "statement_cte_procedure",     "size": 1, "overlap": 0,
                 "metadata": ["database", "schema", "table", "procedure", "query_type"]},
    "api_docs": {"name": "endpoint_method_example",     "size": 600, "overlap": 10,
                 "metadata": ["method", "endpoint", "version", "auth_type"]},
    "email":    {"name": "thread_message_quoted_strip", "size": 500, "overlap": 10,
                 "metadata": ["sender", "recipient", "subject", "date", "thread_id"]},
    "ticket":   {"name": "issue_comment_timeline",      "size": 600, "overlap": 10,
                 "metadata": ["ticket_id", "status", "priority", "assignee", "created_at"]},
    "chat":     {"name": "thread_session_time_window",  "size": 400, "overlap": 15,
                 "metadata": ["channel", "thread_id", "speaker", "timestamp"]},
    "image":    {"name": "ocr_caption_region",          "size": 1, "overlap": 0,
                 "metadata": ["image_id", "bbox", "ocr_text", "caption", "object_labels"]},
    "audio":    {"name": "transcript_time_window",      "size": 60, "overlap": 10,
                 "metadata": ["start_time", "end_time", "speaker", "confidence"]},
    "video":    {"name": "scene_transcript_frame",      "size": 60, "overlap": 5,
                 "metadata": ["scene_id", "timestamp", "frame_refs", "transcript"]},
    "iot":      {"name": "time_window_event_rolling",   "size": 60, "overlap": 5,
                 "metadata": ["device_id", "timestamp", "sensor_type", "quality_flag"]},
    "geospatial": {"name": "tile_polygon_overlap",      "size": 1, "overlap": 10,
                   "metadata": ["lat", "lon", "polygon", "tile_id", "crs"]},
    "graph":    {"name": "node_neighborhood_path",      "size": 1, "overlap": 0,
                 "metadata": ["node_id", "edge_type", "hop_count", "graph_version"]},
}

# ───────────────────────────────────────────────────────────────────
# Use-case overrides (operator spec — high-stakes domains tighten
# chunk boundaries for accuracy at the cost of more chunks)
# ───────────────────────────────────────────────────────────────────
_USE_CASE_OVERRIDES: dict[str, dict[str, Any]] = {
    "legal":      {"name": "hierarchical_section_clause", "size": 400, "overlap": 25},
    "policy":     {"name": "hierarchical_section_clause", "size": 400, "overlap": 25},
    "compliance": {"name": "hierarchical_section_clause", "size": 400, "overlap": 25},
    "code_qa":       {"size": 1, "overlap": 0},  # function-level always
    "incident_search": {"name": "time_window_correlation_id", "size": 500, "overlap": 10},
}


# Default quality checks every chunk goes through (operator spec)
_DEFAULT_QUALITY_CHECKS = [
    "min_token_count",
    "max_token_count",
    "duplicate_check",
    "metadata_complete",
    "pii_scan",
]


def _normalize_file_type(file_type: str) -> str:
    """Map common synonyms to the canonical 23-key vocabulary."""
    canonical_map = {
        "text": "txt", "txt": "txt",
        "pdf": "pdf",
        "docx": "docx", "word": "docx", "doc": "docx",
        "pptx": "ppt", "ppt": "ppt",
        "html": "html", "htm": "html",
        "markdown": "md", "md": "md",
        "csv": "csv",
        "xlsx": "xlsx", "excel": "xlsx", "xls": "xlsx",
        "json": "json",
        "xml": "xml",
        "log": "logs", "logs": "logs",
        "code": "code", "py": "code", "java": "code",
        "sql": "sql",
        "openapi": "api_docs", "api_docs": "api_docs", "swagger": "api_docs",
        "email": "email", "eml": "email",
        "ticket": "ticket", "jira": "ticket",
        "chat": "chat", "slack": "chat",
        "image": "image", "png": "image", "jpg": "image",
        "audio": "audio", "wav": "audio", "mp3": "audio",
        "video": "video", "mp4": "video",
        "iot": "iot", "sensor": "iot",
        "geospatial": "geospatial", "geo": "geospatial",
        "graph": "graph",
    }
    return canonical_map.get(file_type.lower(), file_type.lower())


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return CHUNKING_STRATEGY_SELECTOR_ENABLED


def supported_file_types() -> list[str]:
    """The 23 canonical types the selector handles."""
    return sorted(_STRATEGY_TABLE.keys())


def choose(
    *,
    file_type: str,
    use_case: str = "general",
    cost_priority: str = "balanced",      # "low" | "balanced" | "high"
    accuracy_priority: str = "balanced",  # "low" | "balanced" | "high"
) -> ChunkingStrategy:
    """Realize the operator's pseudocode:

        if file_type in ["pdf","docx"]:
            if use_case in ["legal","policy","compliance"]:
                return "hierarchical_section_clause_chunking"
            return "recursive_section_chunking"
        ...

    Returns a structured ChunkingStrategy. Caller passes it to the
    downstream chunker (Stage-2 wiring).

    Raises ChunkingSelectorDisabled when the env flag is unset.
    """
    if not is_available():
        raise ChunkingSelectorDisabled(
            "Chunking strategy selector disabled. Set "
            "CHUNKING_STRATEGY_SELECTOR_ENABLED=1 to use."
        )

    canonical = _normalize_file_type(file_type)
    if canonical not in _STRATEGY_TABLE:
        # Unknown type — fall back to recursive text chunking with
        # a clear rationale log so operator can grow the table.
        log.warning("unknown file_type=%r — falling back to recursive_text", file_type)
        return ChunkingStrategy(
            strategy_name="recursive_paragraph_sentence",
            file_type=canonical,
            use_case=use_case,
            chunk_size_tokens=500,
            overlap_percent=15,
            metadata_fields=["source_id", "chunk_id", "section", "token_count"],
            quality_checks=list(_DEFAULT_QUALITY_CHECKS),
            rationale=f"unknown file_type={file_type!r}; recursive default",
        )

    base = _STRATEGY_TABLE[canonical]
    name = base["name"]
    size = base["size"]
    overlap = base["overlap"]

    # Apply use-case overrides per the operator spec
    rationale_parts = [f"file_type={canonical}"]
    if use_case in _USE_CASE_OVERRIDES:
        override = _USE_CASE_OVERRIDES[use_case]
        if "name" in override:
            name = override["name"]
        if "size" in override:
            size = override["size"]
        if "overlap" in override:
            overlap = override["overlap"]
        rationale_parts.append(f"use_case_override={use_case}")

    # Cost/accuracy modulation:
    # - high accuracy → smaller chunks, more overlap (more chunks, more recall)
    # - low cost → larger chunks, less overlap (fewer chunks, less recall)
    if accuracy_priority == "high":
        size = max(int(size * 0.7), 100) if size > 1 else size
        overlap = min(overlap + 10, 30) if overlap > 0 else overlap
        rationale_parts.append("accuracy=high (smaller+more overlap)")
    elif cost_priority == "low":
        size = int(size * 1.3) if size > 1 else size
        overlap = max(overlap - 5, 0) if overlap > 0 else overlap
        rationale_parts.append("cost=low (larger+less overlap)")

    return ChunkingStrategy(
        strategy_name=name,
        file_type=canonical,
        use_case=use_case,
        chunk_size_tokens=size,
        overlap_percent=overlap,
        metadata_fields=list(base["metadata"]),
        quality_checks=list(_DEFAULT_QUALITY_CHECKS),
        rationale=" / ".join(rationale_parts),
    )


def status() -> dict[str, Any]:
    return {
        "stage": 1,
        "enabled_env": CHUNKING_STRATEGY_SELECTOR_ENABLED,
        "available": is_available(),
        "supported_file_types_count": len(_STRATEGY_TABLE),
        "supported_file_types": supported_file_types(),
        "use_case_overrides": list(_USE_CASE_OVERRIDES.keys()),
        "default_quality_checks": list(_DEFAULT_QUALITY_CHECKS),
        "wiring_status": "stage-1 selector; Stage-2 wires into ingestion saga BEFORE chunker",
        "next_stage": "Stage-2 — call selector.choose() in ingestion saga before handing text to Chunker",
    }


if __name__ == "__main__":
    import json
    import sys
    print("scripts/chunking_strategy_selector.py — Stage-1 chunking decision engine")
    print("Stage-1 opt-in via CHUNKING_STRATEGY_SELECTOR_ENABLED=1")
    print(f"Supports {len(_STRATEGY_TABLE)} file types per operator spec.")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
