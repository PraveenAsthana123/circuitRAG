"""
Cross-tenant RLS isolation test (Design Area 5).

This is the single most important security test in the repo. If it
passes, tenant A CANNOT read tenant B's rows regardless of app bugs.

Requires a live Postgres (16+) reachable at $DOCUMIND_PG_HOST/PG_PORT.
If no Postgres is available, the test skips with a clear marker — CI
should install one (the workflow uses a `services:` block in a future
PR).
"""
from __future__ import annotations

import os
import uuid

import pytest

pg_host = os.getenv("DOCUMIND_PG_HOST")
pytestmark = pytest.mark.skipif(
    not pg_host,
    reason="RLS test requires a live Postgres (set DOCUMIND_PG_HOST).",
)


@pytest.mark.asyncio
async def test_cross_tenant_read_is_empty():
    """
    Setup:
      - create two tenants
      - insert one document per tenant
    Act (as tenant A):
      - SELECT * FROM ingestion.documents
    Assert:
      - only tenant A's row is visible; tenant B's row is NOT returned
    """
    import asyncpg

    dsn = (
        f"postgresql://"
        f"{os.getenv('DOCUMIND_PG_USER', 'documind')}:"
        f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind')}@"
        f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
        f"{os.getenv('DOCUMIND_PG_PORT', '5432')}/"
        f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
    )
    try:
        conn = await asyncpg.connect(dsn, command_timeout=5)
    except Exception as exc:
        pytest.skip(f"could not connect to Postgres: {exc}")
        return

    try:
        # Admin connection — insert rows without RLS in the way.
        a = uuid.uuid4()
        b = uuid.uuid4()
        await conn.execute(
            "INSERT INTO identity.tenants (id, name, tier) VALUES "
            "($1, 'tenant-A', 'pro'), ($2, 'tenant-B', 'pro') "
            "ON CONFLICT DO NOTHING",
            a, b,
        )
        doc_a = uuid.uuid4()
        doc_b = uuid.uuid4()
        for doc_id, tid, name in [(doc_a, a, "a.pdf"), (doc_b, b, "b.pdf")]:
            await conn.execute(
                """
                INSERT INTO ingestion.documents
                  (id, tenant_id, filename, mime_type, size_bytes,
                   checksum_sha256, blob_uri, state, version)
                VALUES ($1, $2, $3, 'application/pdf', 10, 'x', 's3://x', 'uploaded', 1)
                ON CONFLICT DO NOTHING
                """,
                doc_id, tid, name,
            )

        # Act AS tenant A — set_config scoped to this transaction.
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", str(a),
            )
            rows = await conn.fetch(
                "SELECT id FROM ingestion.documents",
            )
        visible = {r["id"] for r in rows}
        assert doc_a in visible, "tenant A MUST see their own document"
        assert doc_b not in visible, "CRITICAL: tenant A saw tenant B's document — RLS broken"
    finally:
        # Clean up — direct delete via admin conn (BYPASS RLS path).
        await conn.execute("DELETE FROM ingestion.documents WHERE filename IN ('a.pdf', 'b.pdf')")
        await conn.execute("DELETE FROM identity.tenants WHERE name IN ('tenant-A', 'tenant-B')")
        await conn.close()
