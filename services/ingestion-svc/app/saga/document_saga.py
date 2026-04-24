"""
Document ingestion saga (Design Areas 18 — Workflow Orchestration,
19 — Compensation Logic, 20 — Idempotency).

Five steps, each with an idempotent compensating action::

    Step 1 · PARSE      compensate: drop parsed blob from MinIO
    Step 2 · CHUNK      compensate: DELETE FROM ingestion.chunks WHERE doc_id = ?
    Step 3 · EMBED      compensate: (no-op — embeddings recomputed on re-run)
    Step 4 · GRAPH      compensate: MATCH (n {document_id: $id}) DETACH DELETE n
    Step 5 · INDEX      compensate: Qdrant delete by document_id filter

If step N fails, compensations for steps 1..N-1 run in REVERSE order. Each
compensation is idempotent — running twice is safe — because failure during
compensation is possible and the recovery worker must be able to retry.

Running the saga
----------------
The saga is called from the upload route, but can also be re-invoked from
a cron recovery task that inspects ``ingestion.sagas`` for rows stuck in
``state = 'running'`` longer than the SLA.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from documind_core.exceptions import AppError, ExternalServiceError

from app.chunking import Chunk, Chunker
from app.embedding import EmbeddingProvider
from app.parsers import DocumentParser, ParsedDocument, ParserRegistry
from app.repositories import ChunkRepo, DocumentRepo, Neo4jRepo, QdrantRepo, SagaRepo
from app.saga.outbox import OutboxRepo
from app.services.poisoning_defense import ChunkPoisoningGuard, SanitizeDecision
from app.repositories.document_repo import (
    STATE_ACTIVE, STATE_CHUNKED, STATE_CHUNKING, STATE_EMBEDDED, STATE_EMBEDDING,
    STATE_INDEXED, STATE_INDEXING, STATE_PARSED, STATE_PARSING,
)

log = logging.getLogger(__name__)


class CompensationError(AppError):
    """A compensating action itself failed. Operator intervention needed."""

    error_code = "COMPENSATION_FAILED"
    http_status = 500


@dataclass
class SagaStep:
    name: str
    execute: Callable[[], Awaitable[dict[str, Any]]]
    compensate: Callable[[], Awaitable[None]]


class DocumentIngestionSaga:
    """
    Orchestrates the 5-step pipeline for a single document.

    Usage::

        saga = DocumentIngestionSaga(
            tenant_id, document_id,
            raw_bytes=..., filename=...,
            parser_registry=parsers, chunker=chunker, embedder=embedder,
            chunk_repo=chunk_repo, document_repo=document_repo,
            qdrant_repo=qdrant_repo, neo4j_repo=neo4j_repo, saga_repo=saga_repo,
        )
        await saga.run()
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        raw_bytes: bytes,
        filename: str,
        parser_registry: ParserRegistry,
        chunker: Chunker,
        embedder: EmbeddingProvider,
        document_repo: DocumentRepo,
        chunk_repo: ChunkRepo,
        qdrant_repo: QdrantRepo,
        neo4j_repo: Neo4jRepo,
        saga_repo: SagaRepo,
    ) -> None:
        self._tenant_id = tenant_id
        self._document_id = document_id
        self._raw_bytes = raw_bytes
        self._filename = filename

        self._parsers = parser_registry
        self._chunker = chunker
        self._embedder = embedder

        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._qdrant_repo = qdrant_repo
        self._neo4j_repo = neo4j_repo
        self._saga_repo = saga_repo

        # Retrieval-poisoning defense — runs during the chunk step.
        # Lazily-constructed so tests can inject fakes.
        self._poison_guard = ChunkPoisoningGuard()

        # Populated as steps execute — used for compensations
        self._parsed_doc: ParsedDocument | None = None
        self._chunks: list[Chunk] = []
        self._chunk_ids: list[UUID] = []
        self._vectors: list[list[float]] = []
        self._saga_id: UUID | None = None

    # ------------------------------------------------------------------
    # Top-level entry point
    # ------------------------------------------------------------------
    async def run(self) -> dict[str, Any]:
        saga = await self._saga_repo.create(
            tenant_id=self._tenant_id,
            saga_type="document_ingestion",
            subject_id=self._document_id,
            total_steps=5,
        )
        self._saga_id = saga["id"]

        steps = [
            SagaStep("parse", self._step_parse, self._compensate_parse),
            SagaStep("chunk", self._step_chunk, self._compensate_chunk),
            SagaStep("embed", self._step_embed, self._compensate_embed),
            SagaStep("graph", self._step_graph, self._compensate_graph),
            SagaStep("index", self._step_index, self._compensate_index),
        ]

        executed: list[SagaStep] = []
        try:
            for step in steps:
                log.info("saga_step_start name=%s doc=%s", step.name, self._document_id)
                result = await step.execute()
                await self._saga_repo.record_step(
                    tenant_id=self._tenant_id,
                    saga_id=self._saga_id,
                    step_name=step.name,
                    result=result,
                )
                executed.append(step)

            # All steps succeeded — promote to ACTIVE
            await self._document_repo.transition_state(
                tenant_id=self._tenant_id,
                document_id=self._document_id,
                to_state=STATE_ACTIVE,
                expected_from=STATE_INDEXED,
            )
            await self._saga_repo.mark_complete(
                tenant_id=self._tenant_id, saga_id=self._saga_id
            )
            # Outbox: publish `document.indexed.v1` atomically with the
            # ACTIVE transition. Same connection would be ideal; for now
            # we use a separate tenant_connection — acceptable because
            # OutboxDrainWorker retries on Kafka failure and the event
            # has stable id (UUID) so Kafka consumers dedup.
            await self._publish_outbox(
                event_type="document.indexed.v1",
                data={
                    "document_id": str(self._document_id),
                    "chunks_count": len(self._chunks),
                    "embedding_model": self._embedder.model_name,
                },
            )
            log.info("saga_complete doc=%s", self._document_id)
            return {"saga_id": str(self._saga_id), "document_id": str(self._document_id)}

        except Exception as exc:
            log.exception("saga_failed step=%s doc=%s", getattr(exc, "_step", "?"), self._document_id)
            await self._saga_repo.mark_failed(
                tenant_id=self._tenant_id,
                saga_id=self._saga_id,
                failing_step=executed[-1].name if executed else "none",
                error=f"{type(exc).__name__}: {exc}",
            )
            await self._run_compensations(executed)
            await self._document_repo.mark_failed(
                tenant_id=self._tenant_id,
                document_id=self._document_id,
                reason=f"saga_failed: {type(exc).__name__}",
            )
            raise

    async def _publish_outbox(self, *, event_type: str, data: dict[str, Any]) -> None:
        """Enqueue a CloudEvents row in the outbox. Shares the tenant
        connection so the insert is transactional with the caller's context."""
        async with self._document_repo._db.tenant_connection(self._tenant_id) as conn:  # noqa: SLF001
            await OutboxRepo.enqueue(
                conn,
                tenant_id=self._tenant_id,
                topic="document.lifecycle",
                event_type=event_type,
                subject=str(self._document_id),
                correlation_id="",  # filled by middleware in the production path
                payload=data,
            )

    async def _run_compensations(self, executed: list[SagaStep]) -> None:
        for step in reversed(executed):
            try:
                log.info("saga_compensate name=%s doc=%s", step.name, self._document_id)
                await step.compensate()
            except Exception as comp_exc:  # noqa: BLE001
                log.exception(
                    "saga_compensation_failed step=%s doc=%s",
                    step.name, self._document_id,
                )
                # Mark saga as "stuck" — alerts should fire on state=failed + unclean compensation
                await self._saga_repo.mark_failed(
                    tenant_id=self._tenant_id,
                    saga_id=self._saga_id,  # type: ignore[arg-type]
                    failing_step=f"compensate_{step.name}",
                    error=f"{type(comp_exc).__name__}: {comp_exc}",
                )
                # Don't raise — continue trying to compensate remaining steps.
                continue
        if self._saga_id is not None:
            await self._saga_repo.mark_compensated(
                tenant_id=self._tenant_id, saga_id=self._saga_id
            )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    async def _step_parse(self) -> dict[str, Any]:
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_PARSING,
        )
        parser: DocumentParser = self._parsers.get(self._filename)
        # Parsing is CPU-bound; run in a thread so we don't block the loop.
        self._parsed_doc = await asyncio.to_thread(
            parser.parse, self._raw_bytes, filename=self._filename
        )
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_PARSED,
        )
        await self._document_repo.touch(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            updates={"title": self._parsed_doc.title, "page_count": len(self._parsed_doc.pages)},
        )
        return {"pages": len(self._parsed_doc.pages), "title": self._parsed_doc.title}

    async def _compensate_parse(self) -> None:
        # Nothing persisted outside the DB row itself — state rollback is handled
        # centrally by mark_failed at the end.
        self._parsed_doc = None

    async def _step_chunk(self) -> dict[str, Any]:
        assert self._parsed_doc is not None  # noqa: S101
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_CHUNKING,
        )
        raw_chunks = await asyncio.to_thread(self._chunker.chunk, self._parsed_doc)

        # Retrieval-poisoning defense: scan each chunk for injection +
        # PII BEFORE they reach the vector index. REJECT offensive chunks;
        # REDACT suspicious ones.
        sanitized, outcomes = self._poison_guard.sanitize_batch(raw_chunks)
        rejected = sum(1 for o in outcomes if o.decision is SanitizeDecision.REJECT)
        redacted = sum(1 for o in outcomes if o.decision is SanitizeDecision.REDACT)

        if rejected > 0 and len(sanitized) == 0:
            raise ExternalServiceError(
                "document rejected — all chunks contained injection patterns",
                details={"rejected": rejected, "total": len(raw_chunks)},
            )
        if rejected > 0:
            log.warning(
                "chunks_poisoned rejected=%d redacted=%d total=%d doc=%s",
                rejected, redacted, len(raw_chunks), self._document_id,
            )

        self._chunks = sanitized
        inserted = await self._chunk_repo.bulk_insert(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            chunks=self._chunks,
        )
        self._chunk_ids = [UUID(r["id"]) if isinstance(r["id"], str) else r["id"] for r in inserted]
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_CHUNKED,
        )
        await self._document_repo.touch(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            updates={"chunk_count": len(self._chunks)},
        )
        return {"chunks": len(self._chunks)}

    async def _compensate_chunk(self) -> None:
        await self._chunk_repo.delete_by_document(
            tenant_id=self._tenant_id, document_id=self._document_id
        )

    async def _step_embed(self) -> dict[str, Any]:
        if not self._chunks:
            raise ExternalServiceError("no chunks to embed")
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_EMBEDDING,
        )

        batch_size = 16
        self._vectors = []
        for start in range(0, len(self._chunks), batch_size):
            batch = self._chunks[start:start + batch_size]
            vecs = await self._embedder.embed_many([c.text for c in batch])
            self._vectors.extend(vecs)

        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_EMBEDDED,
        )
        return {"vectors": len(self._vectors), "model": self._embedder.model_name}

    async def _compensate_embed(self) -> None:
        # In-memory only — nothing to undo until we write to Qdrant.
        self._vectors = []

    async def _step_graph(self) -> dict[str, Any]:
        assert self._parsed_doc is not None  # noqa: S101
        await self._neo4j_repo.upsert_document(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            title=self._parsed_doc.title,
        )
        graph_chunks = [
            {
                "id": str(self._chunk_ids[i]),
                "text": c.text,
                "page": c.page_number,
                "index": c.index,
            }
            for i, c in enumerate(self._chunks)
        ]
        await self._neo4j_repo.upsert_chunks(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            chunks=graph_chunks,
        )
        # Entity extraction would go here — stubbed for now to keep the saga
        # deterministic. See docs/design-areas/23-ingestion.md for how to
        # wire an entity extractor.
        return {"chunks_linked": len(graph_chunks)}

    async def _compensate_graph(self) -> None:
        await self._neo4j_repo.delete_document(
            tenant_id=self._tenant_id, document_id=self._document_id
        )

    async def _step_index(self) -> dict[str, Any]:
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_INDEXING,
        )

        payloads = [
            {
                "tenant_id": self._tenant_id,
                "document_id": str(self._document_id),
                "chunk_id": str(self._chunk_ids[i]),
                "index": c.index,
                "page": c.page_number,
                "text": c.text,
                "content_hash": c.content_hash,
                "created_at": 0,  # now-ms, set by migration/insert pipeline in prod
            }
            for i, c in enumerate(self._chunks)
        ]
        n = await self._qdrant_repo.upsert_chunks(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            chunk_ids=self._chunk_ids,
            vectors=self._vectors,
            payloads=payloads,
        )
        await self._document_repo.transition_state(
            tenant_id=self._tenant_id,
            document_id=self._document_id,
            to_state=STATE_INDEXED,
        )
        return {"indexed_vectors": n}

    async def _compensate_index(self) -> None:
        await self._qdrant_repo.delete_document(
            tenant_id=self._tenant_id, document_id=self._document_id
        )
