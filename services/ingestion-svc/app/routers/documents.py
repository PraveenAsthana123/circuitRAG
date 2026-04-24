"""
Document HTTP routes (Design Area 23 — Ingestion Service API).

These are THIN — no SQL, no business logic. The router extracts request
data, calls the :class:`IngestionService`, and serializes the response.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from documind_core.exceptions import ValidationError
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status

from app.schemas import ChunkView, DocumentDetail, DocumentList, DocumentSummary, UploadResponse
from app.services import IngestionService

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _get_service(request: Request) -> IngestionService:
    svc: IngestionService | None = getattr(request.app.state, "ingestion_service", None)
    if svc is None:
        raise RuntimeError("ingestion_service not initialized")
    return svc


ServiceDep = Annotated[IngestionService, Depends(_get_service)]


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload(
    request: Request,
    service: ServiceDep,
    file: UploadFile = File(...),
    sync: bool = Form(default=False, description="Run ingestion inline vs background"),
) -> UploadResponse:
    tenant_id: str = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")

    data = await file.read()
    result = await service.ingest_upload(
        tenant_id=tenant_id,
        user_id=None,  # identity-svc would inject this via JWT in production
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        run_saga_inline=sync,
    )
    return UploadResponse(
        document_id=result.document_id,
        state=result.state,
        saga_id=result.saga_id,
        message="Ingestion complete" if sync else "Ingestion started",
    )


@router.get("", response_model=DocumentList)
async def list_documents(
    request: Request,
    service: ServiceDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    state: str | None = Query(None, description="Filter by document state"),
) -> DocumentList:
    tenant_id: str = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")

    items, total = await service.list_documents(
        tenant_id=tenant_id, offset=offset, limit=limit, state=state
    )
    return DocumentList(
        items=[DocumentSummary(**item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < total,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    request: Request,
    service: ServiceDep,
) -> DocumentDetail:
    tenant_id: str = getattr(request.state, "tenant_id", "") or ""
    doc = await service.get_document(tenant_id=tenant_id, document_id=document_id)
    return DocumentDetail(**doc)


@router.get("/{document_id}/chunks", response_model=list[ChunkView])
async def list_chunks(
    document_id: UUID,
    request: Request,
    service: ServiceDep,
) -> list[ChunkView]:
    tenant_id: str = getattr(request.state, "tenant_id", "") or ""
    chunks = await service.list_chunks(tenant_id=tenant_id, document_id=document_id)
    return [ChunkView(**c) for c in chunks]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    request: Request,
    service: ServiceDep,
) -> None:
    tenant_id: str = getattr(request.state, "tenant_id", "") or ""
    await service.delete_document(tenant_id=tenant_id, document_id=document_id)
