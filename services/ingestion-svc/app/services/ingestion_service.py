"""
IngestionService — business-logic wrapper over the saga orchestrator.

Responsibilities:

* Validate the upload (size, extension, checksum).
* Persist the raw blob to MinIO.
* Create the document row.
* Kick off the saga.
* Surface documents + chunks to the API.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from documind_core.db_client import DbClient
from documind_core.exceptions import ValidationError

from app.chunking import Chunker
from app.core.config import IngestionSettings
from app.embedding import EmbeddingProvider
from app.parsers import ParserRegistry
from app.repositories import ChunkRepo, DocumentRepo, Neo4jRepo, QdrantRepo, SagaRepo
from app.saga import DocumentIngestionSaga

from .blob_service import BlobService

log = logging.getLogger(__name__)


@dataclass
class UploadResult:
    document_id: UUID
    state: str
    saga_id: UUID | None


class IngestionService:
    def __init__(
        self,
        *,
        settings: IngestionSettings,
        parsers: ParserRegistry,
        chunker: Chunker,
        embedder: EmbeddingProvider,
        document_repo: DocumentRepo,
        chunk_repo: ChunkRepo,
        saga_repo: SagaRepo,
        qdrant_repo: QdrantRepo,
        neo4j_repo: Neo4jRepo,
        blob_service: BlobService,
        db: DbClient,
    ) -> None:
        self._settings = settings
        self._parsers = parsers
        self._chunker = chunker
        self._embedder = embedder
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._saga_repo = saga_repo
        self._qdrant_repo = qdrant_repo
        self._neo4j_repo = neo4j_repo
        self._blob_service = blob_service
        self._db = db

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_upload(self, *, filename: str, size: int) -> None:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self._settings.allowed_extensions_list:
            raise ValidationError(
                f"Extension '{ext}' not allowed",
                details={"allowed": self._settings.allowed_extensions_list},
            )
        if size > self._settings.max_upload_mb * 1024 * 1024:
            raise ValidationError(
                f"File too large ({size} bytes > {self._settings.max_upload_mb} MB)",
            )
        if size == 0:
            raise ValidationError("File is empty")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    async def ingest_upload(
        self,
        *,
        tenant_id: str,
        user_id: UUID | None,
        filename: str,
        content_type: str,
        data: bytes,
        run_saga_inline: bool = False,
    ) -> UploadResult:
        self._validate_upload(filename=filename, size=len(data))
        checksum = hashlib.sha256(data).hexdigest()

        # 1. Store raw blob (outside the saga so failure here never leaves
        #    orphan state — we haven't written a DB row yet.)
        await asyncio.to_thread(self._blob_service.ensure_bucket)

        # Provisional object_name based on checksum so retries deduplicate.
        provisional_id = UUID(bytes=hashlib.md5(data).digest())  # noqa: S324
        blob_uri = await asyncio.to_thread(
            self._blob_service.put,
            tenant_id=tenant_id,
            document_id=provisional_id,
            filename=filename,
            data=data,
            content_type=content_type,
        )

        # 2. Create the document row
        doc = await self._document_repo.create(
            tenant_id=tenant_id,
            filename=filename,
            mime_type=content_type or "application/octet-stream",
            size_bytes=len(data),
            checksum_sha256=checksum,
            blob_uri=blob_uri,
            uploaded_by=user_id,
        )
        document_id = doc["id"]

        # 3. Kick off the saga
        saga = DocumentIngestionSaga(
            tenant_id=tenant_id,
            document_id=document_id,
            raw_bytes=data,
            filename=filename,
            parser_registry=self._parsers,
            chunker=self._chunker,
            embedder=self._embedder,
            document_repo=self._document_repo,
            chunk_repo=self._chunk_repo,
            qdrant_repo=self._qdrant_repo,
            neo4j_repo=self._neo4j_repo,
            saga_repo=self._saga_repo,
            db=self._db,
        )

        if run_saga_inline:
            result = await saga.run()
            return UploadResult(
                document_id=document_id,
                state="active",
                saga_id=UUID(result["saga_id"]),
            )
        else:
            # Fire-and-forget background task. In production this would be a
            # Kafka event that Ingestion consumers pick up — using asyncio for
            # the dev-fallback path (docker-compose).
            asyncio.create_task(self._run_saga_bg(saga))
            return UploadResult(
                document_id=document_id,
                state=doc["state"],
                saga_id=None,
            )

    @staticmethod
    async def _run_saga_bg(saga: DocumentIngestionSaga) -> None:
        try:
            await saga.run()
        except Exception:
            # Already logged inside the saga. Swallow here so the background
            # task doesn't crash the loop with an unhandled exception.
            log.debug("saga_background_error_swallowed")

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def get_document(self, *, tenant_id: str, document_id: UUID) -> dict[str, Any]:
        return await self._document_repo.get(tenant_id=tenant_id, document_id=document_id)

    async def list_documents(
        self, *, tenant_id: str, offset: int, limit: int, state: str | None
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._document_repo.list(
            tenant_id=tenant_id, offset=offset, limit=limit, state=state
        )

    async def list_chunks(self, *, tenant_id: str, document_id: UUID) -> list[dict[str, Any]]:
        return await self._chunk_repo.list_by_document(
            tenant_id=tenant_id, document_id=document_id
        )

    async def delete_document(self, *, tenant_id: str, document_id: UUID) -> None:
        """Full cascade delete — Postgres row, chunks, vectors, graph, blob."""
        doc = await self._document_repo.get(tenant_id=tenant_id, document_id=document_id)
        # Order matters: clean satellite stores before the central record.
        await self._qdrant_repo.delete_document(tenant_id=tenant_id, document_id=document_id)
        await self._neo4j_repo.delete_document(tenant_id=tenant_id, document_id=document_id)
        await self._chunk_repo.delete_by_document(tenant_id=tenant_id, document_id=document_id)
        await asyncio.to_thread(self._blob_service.delete, uri=doc["blob_uri"])
        await self._document_repo.delete(tenant_id=tenant_id, document_id=document_id)
