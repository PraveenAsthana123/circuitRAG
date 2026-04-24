#!/usr/bin/env python3
"""
Seed a demo tenant + sample documents.

Usage::

    python scripts/seed_demo.py

Creates a ``demo-tenant`` row in identity.tenants (if absent), writes a
sample plain-text "document" in data/samples/, and prints the demo tenant
UUID for use in X-Tenant-ID headers.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID

import asyncpg

DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"

SAMPLE_DOCS = {
    "documind-overview.txt": """\
DocuMind is an enterprise document-intelligence platform. It ingests PDFs, DOCX,
HTML, and Markdown files; chunks them with a recursive token-aware splitter; and
generates embeddings via a local Ollama server (nomic-embed-text). Chunks are
stored in Qdrant for vector search and in Neo4j for entity-based graph search.

Retrieval uses a hybrid strategy: a vector search and an entity-graph search run
in parallel; their results are fused with Reciprocal Rank Fusion. The top-K
chunks feed into a versioned prompt template that runs through an Ollama LLM
(llama3.1:8b). Output passes through a guardrail layer that checks citation
validity, PII presence, and confidence, before returning to the user.

Every request carries a correlation ID. Every log line is JSON. Every cache
key is tenant-namespaced. Every SQL table has Row-Level Security. This is
what production-base looks like.
""",
    "saga-pattern.txt": """\
The saga pattern is DocuMind's answer to distributed transactions across
PostgreSQL, Qdrant, and Neo4j. It runs a sequence of local transactions and,
on failure, executes compensating actions in reverse order.

The ingestion saga has five steps: parse, chunk, embed, graph, index. If the
embed step fails, the chunk step's compensation deletes the rows it wrote;
the parse step's compensation drops the parsed blob. Each compensation is
idempotent — running it twice is safe — so a crash during compensation can
be retried without corrupting state.

Saga progress is persisted in ingestion.sagas, so if the service crashes
mid-flight, a boot-time recovery task can resume or compensate.
""",
}


def dsn() -> str:
    host = os.getenv("DOCUMIND_PG_HOST", "localhost")
    port = os.getenv("DOCUMIND_PG_PORT", "5432")
    db = os.getenv("DOCUMIND_PG_DB", "documind")
    user = os.getenv("DOCUMIND_PG_USER", "documind")
    pw = os.getenv("DOCUMIND_PG_PASSWORD", "documind")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


async def seed() -> None:
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute(
            """
            INSERT INTO identity.tenants (id, name, tier)
            VALUES ($1, $2, 'pro')
            ON CONFLICT (id) DO NOTHING
            """,
            DEMO_TENANT_ID, "demo-tenant",
        )
    finally:
        await conn.close()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in SAMPLE_DOCS.items():
        path = SAMPLES_DIR / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    print(f"Seeded demo tenant: {DEMO_TENANT_ID}")
    print(f"Sample docs at   : {SAMPLES_DIR}")
    print()
    print(f"Set in frontend .env: VITE_DEMO_TENANT_ID={DEMO_TENANT_ID}")


if __name__ == "__main__":
    asyncio.run(seed())
