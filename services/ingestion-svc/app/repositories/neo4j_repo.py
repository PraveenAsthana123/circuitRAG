"""
Neo4j repository (Design Area 48 — Graph Strategy).

Stores the knowledge graph:

    (:Document {id, tenant_id, title})
       └─[:HAS_CHUNK]─► (:Chunk {id, tenant_id, text, page})
                             └─[:MENTIONS]─► (:Entity {name, type, tenant_id})
                                                   └─[:RELATED_TO]─► (:Entity)

Every node carries ``tenant_id`` — every Cypher query is parameterized
with ``$tenant_id`` as the first filter. A unit test proves cross-tenant
queries return empty.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from neo4j import AsyncGraphDatabase

log = logging.getLogger(__name__)


class Neo4jRepo:
    def __init__(self, *, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def ensure_constraints(self) -> None:
        """Create uniqueness + existence constraints (safe to re-run)."""
        queries = [
            # Unique IDs scoped by tenant
            "CREATE CONSTRAINT document_unique IF NOT EXISTS "
            "FOR (d:Document) REQUIRE (d.tenant_id, d.id) IS UNIQUE",
            "CREATE CONSTRAINT chunk_unique IF NOT EXISTS "
            "FOR (c:Chunk) REQUIRE (c.tenant_id, c.id) IS UNIQUE",
            "CREATE CONSTRAINT entity_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.tenant_id, e.name) IS UNIQUE",
            # Indexes for tenant-scoped lookups
            "CREATE INDEX document_tenant IF NOT EXISTS FOR (d:Document) ON (d.tenant_id)",
            "CREATE INDEX chunk_tenant IF NOT EXISTS FOR (c:Chunk) ON (c.tenant_id)",
            "CREATE INDEX entity_tenant IF NOT EXISTS FOR (e:Entity) ON (e.tenant_id)",
        ]
        async with self._driver.session() as s:
            for q in queries:
                await s.run(q)
        log.info("neo4j_constraints_ensured")

    async def upsert_document(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        title: str,
    ) -> None:
        async with self._driver.session() as s:
            await s.run(
                """
                MERGE (d:Document {tenant_id: $tid, id: $did})
                SET d.title = $title, d.updated_at = datetime()
                """,
                tid=tenant_id, did=str(document_id), title=title,
            )

    async def upsert_chunks(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        chunks: list[dict[str, Any]],
    ) -> None:
        if not chunks:
            return
        async with self._driver.session() as s:
            await s.run(
                """
                MATCH (d:Document {tenant_id: $tid, id: $did})
                UNWIND $chunks AS c
                MERGE (ch:Chunk {tenant_id: $tid, id: c.id})
                SET ch.text = c.text,
                    ch.page = c.page,
                    ch.index = c.index,
                    ch.updated_at = datetime()
                MERGE (d)-[:HAS_CHUNK]->(ch)
                """,
                tid=tenant_id, did=str(document_id), chunks=chunks,
            )
        log.info("neo4j_chunks_upserted document=%s n=%d", document_id, len(chunks))

    async def link_entities(
        self,
        *,
        tenant_id: str,
        chunk_id: UUID,
        entities: list[dict[str, Any]],
    ) -> None:
        """Create entity nodes and link them to a chunk via :MENTIONS."""
        if not entities:
            return
        async with self._driver.session() as s:
            await s.run(
                """
                MATCH (ch:Chunk {tenant_id: $tid, id: $cid})
                UNWIND $entities AS e
                MERGE (ent:Entity {tenant_id: $tid, name: e.name})
                SET ent.type = coalesce(e.type, ent.type)
                MERGE (ch)-[:MENTIONS]->(ent)
                """,
                tid=tenant_id, cid=str(chunk_id), entities=entities,
            )

    async def delete_document(self, *, tenant_id: str, document_id: UUID) -> None:
        async with self._driver.session() as s:
            await s.run(
                """
                MATCH (d:Document {tenant_id: $tid, id: $did})
                OPTIONAL MATCH (d)-[:HAS_CHUNK]->(ch:Chunk)
                DETACH DELETE d, ch
                """,
                tid=tenant_id, did=str(document_id),
            )
        log.info("neo4j_document_deleted id=%s", document_id)

    async def aclose(self) -> None:
        await self._driver.close()
