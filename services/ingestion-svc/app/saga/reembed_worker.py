"""
Re-embed worker (Design Area 39 — Embedding Lifecycle).

When the embedding model changes (e.g. `nomic-embed-text` →
`bge-m3` with different dimensionality), existing chunks need to be
re-embedded under the new model. This worker scans for chunks whose
`metadata->>'embedding_model'` doesn't match the current model and
re-embeds them in batches, atomically via the saga (so Qdrant writes
+ chunk metadata updates are transactional per batch).

Run it:
* From ingestion-svc startup lifespan as a low-priority task
* From a cron / K8s Job for big backfills
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from documind_core.db_client import DbClient

from app.embedding import EmbeddingProvider
from app.repositories import QdrantRepo

log = logging.getLogger(__name__)


class ReembedWorker:
    def __init__(
        self,
        *,
        db: DbClient,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        batch_size: int = 32,
        idle_sleep_s: float = 30.0,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._qdrant = qdrant
        self._batch = batch_size
        self._idle = idle_sleep_s
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._loop())
        log.info("reembed_worker_started target_model=%s batch=%d",
                 self._embedder.model_name, self._batch)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                n = await self._run_once()
                if n == 0:
                    await asyncio.sleep(self._idle)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("reembed_worker_error")
                await asyncio.sleep(self._idle)

    async def _run_once(self) -> int:
        """Pick a batch of stale chunks, re-embed them, upsert to Qdrant."""
        current_model = self._embedder.model_name
        # Use admin_connection so we scan across tenants. A per-tenant
        # variant is safer for very large corpora.
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, document_id, text, index, page_number, metadata
                FROM ingestion.chunks
                WHERE COALESCE(metadata->>'embedding_model', '') <> $1
                ORDER BY updated_at ASC
                LIMIT $2
                FOR UPDATE SKIP LOCKED
                """,
                current_model, self._batch,
            )
            if not rows:
                return 0

            texts = [r["text"] for r in rows]
            vectors = await self._embedder.embed_many(texts)

            # Group by (tenant, document) for Qdrant upsert batching.
            by_doc: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for row, vec in zip(rows, vectors, strict=True):
                key = (str(row["tenant_id"]), str(row["document_id"]))
                by_doc.setdefault(key, []).append({"row": dict(row), "vec": vec})

            for (tenant_id, document_id), items in by_doc.items():
                chunk_ids = [item["row"]["id"] for item in items]
                vecs = [item["vec"] for item in items]
                payloads = [
                    {
                        "chunk_id": str(item["row"]["id"]),
                        "index": item["row"]["index"],
                        "page": item["row"]["page_number"],
                        "text": item["row"]["text"],
                        "content_hash": (
                            item["row"]["metadata"].get("content_hash")
                            if isinstance(item["row"]["metadata"], dict)
                            else ""
                        ),
                    }
                    for item in items
                ]
                await self._qdrant.upsert_chunks(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_ids=chunk_ids,
                    vectors=vecs,
                    payloads=payloads,
                )

            # Mark chunks as re-embedded under the new model.
            await conn.execute(
                """
                UPDATE ingestion.chunks
                SET metadata = COALESCE(metadata, '{}'::jsonb)
                               || jsonb_build_object('embedding_model', $1::text,
                                                     'embedding_updated_at',
                                                      NOW()::text),
                    updated_at = NOW()
                WHERE id = ANY($2::uuid[])
                """,
                current_model, [r["id"] for r in rows],
            )
            log.info(
                "reembed_batch done count=%d target_model=%s docs=%d",
                len(rows), current_model, len(by_doc),
            )
            return len(rows)
