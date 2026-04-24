"""
Graph search over Neo4j (Design Area 48).

Entity-aware retrieval: extract named entities from the query, then find
chunks that mention those entities. Ranks by mention count.

A real implementation would use a proper NER model (spaCy, LLM). For the
demo we do coarse keyword matching — same API, easy to swap.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from neo4j import AsyncGraphDatabase

log = logging.getLogger(__name__)


class GraphSearcher:
    def __init__(self, *, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    @staticmethod
    def _extract_entities(query: str) -> list[str]:
        """Naive NER — capitalized words + multi-word capitalized sequences."""
        # Real prod: swap in spaCy NER or LLM entity extraction.
        matches = re.findall(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*", query)
        return list({m.strip() for m in matches if len(m) > 2})

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        entities = self._extract_entities(query)
        if not entities:
            return []

        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (ent:Entity {tenant_id: $tid})-[:MENTIONS]-(ch:Chunk {tenant_id: $tid})
                WHERE ent.name IN $entities
                WITH ch, count(ent) AS mentions
                MATCH (d:Document {tenant_id: $tid})-[:HAS_CHUNK]->(ch)
                RETURN ch.id AS chunk_id, d.id AS document_id, ch.text AS text,
                       ch.page AS page, mentions
                ORDER BY mentions DESC
                LIMIT $limit
                """,
                tid=tenant_id, entities=entities, limit=top_k,
            )
            rows = [dict(r) async for r in result]

        # Normalize score to 0..1 against the max mention count
        max_mentions = max((r["mentions"] for r in rows), default=1)
        hits = [
            {
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "text": r["text"],
                "page_number": r["page"],
                "score": r["mentions"] / max_mentions,
                "source": "graph",
            }
            for r in rows
        ]
        log.info(
            "graph_search tenant=%s entities=%d hits=%d",
            tenant_id, len(entities), len(hits),
        )
        return hits

    async def aclose(self) -> None:
        await self._driver.close()
