"""
Cross-tenant RLS isolation test (Design Area 5 — most important security test).

Runs against a live Postgres when env vars are set. The test uses TWO
connections:

  documind_ops  (BYPASSRLS)  — seeds test rows for both tenants.
  documind_app  (RLS-enforced) — reads while scoped to tenant A, must
                                  NOT see tenant B's rows.

If this test fails, RLS is broken and the repo ships with a tenant-
data-leak bug. Do NOT relax the assertion.

Environment:
  DOCUMIND_PG_HOST, DOCUMIND_PG_PORT, DOCUMIND_PG_DB — required.
  DOCUMIND_PG_APP_USER      (default: documind_app)
  DOCUMIND_PG_APP_PASSWORD  (default: documind_app)
  DOCUMIND_PG_OPS_USER      (default: documind_ops)
  DOCUMIND_PG_OPS_PASSWORD  (default: documind_ops)
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DOCUMIND_PG_HOST"),
    reason="live Postgres required (set DOCUMIND_PG_HOST)",
)


def _dsn(user_env: str, pwd_env: str, default_user: str) -> str:
    return (
        f"postgresql://"
        f"{os.getenv(user_env, default_user)}:"
        f"{os.getenv(pwd_env, default_user)}@"
        f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
        f"{os.getenv('DOCUMIND_PG_PORT', '5432')}/"
        f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
    )


@pytest.mark.asyncio
async def test_cross_tenant_read_is_empty():
    import asyncpg

    ops_dsn = _dsn("DOCUMIND_PG_OPS_USER", "DOCUMIND_PG_OPS_PASSWORD", "documind_ops")
    app_dsn = _dsn("DOCUMIND_PG_APP_USER", "DOCUMIND_PG_APP_PASSWORD", "documind_app")

    try:
        ops = await asyncpg.connect(ops_dsn, command_timeout=5)
        app = await asyncpg.connect(app_dsn, command_timeout=5)
    except Exception as exc:
        pytest.skip(f"could not connect: {exc}")
        return

    a = uuid.uuid4()
    b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    try:
        # Seed BOTH tenants via ops (BYPASSRLS).
        await ops.execute(
            "INSERT INTO identity.tenants (id, name, tier) VALUES "
            "($1, 'rls-test-A', 'pro'), ($2, 'rls-test-B', 'pro') "
            "ON CONFLICT (id) DO NOTHING",
            a, b,
        )
        for doc_id, tid, name in [(doc_a, a, "a.pdf"), (doc_b, b, "b.pdf")]:
            await ops.execute(
                """
                INSERT INTO ingestion.documents
                    (id, tenant_id, filename, mime_type, size_bytes,
                     checksum_sha256, blob_uri, state, version)
                VALUES ($1, $2, $3, 'application/pdf', 10, 'x', 's3://x',
                        'uploaded', 1)
                """,
                doc_id, tid, name,
            )

        # Read as tenant A through the RLS-enforced app role.
        async with app.transaction():
            await app.execute(
                "SELECT set_config('app.current_tenant', $1, true)",
                str(a),
            )
            rows = await app.fetch("SELECT id FROM ingestion.documents")

        visible = {r["id"] for r in rows}
        assert doc_a in visible, "tenant A MUST see their own document"
        assert doc_b not in visible, (
            "CRITICAL: tenant A saw tenant B's document — RLS broken"
        )

        # Also prove: UNSET tenant → NO rows visible
        async with app.transaction():
            # Do not set app.current_tenant
            rows_empty = await app.fetch("SELECT id FROM ingestion.documents")
        assert rows_empty == [], (
            "with no app.current_tenant, app role should see ZERO rows"
        )
    finally:
        await ops.execute(
            "DELETE FROM ingestion.documents WHERE id = ANY($1::uuid[])",
            [doc_a, doc_b],
        )
        await ops.execute(
            "DELETE FROM identity.tenants WHERE id = ANY($1::uuid[])",
            [a, b],
        )
        await ops.close()
        await app.close()
