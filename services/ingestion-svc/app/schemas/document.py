"""Pydantic schemas (Design Area 30 — API Contracts)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    id: UUID
    filename: str
    title: str | None = None
    state: str
    size_bytes: int
    page_count: int | None = None
    chunk_count: int | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    mime_type: str
    checksum_sha256: str
    blob_uri: str
    error_reason: str | None = None
    version: int


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    total: int
    offset: int
    limit: int
    has_more: bool


class ChunkView(BaseModel):
    id: UUID
    index: int
    page_number: int
    token_count: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    document_id: UUID
    state: str
    saga_id: UUID | None = None
    message: str = "Ingestion started"
