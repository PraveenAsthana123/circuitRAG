#!/usr/bin/env python3
"""Bootstrap Postgres objects for agent-orchestrator-svc."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

from scripts.migrate import apply as apply_migrations

ROOT = Path(__file__).resolve().parents[3]
POSTGRES_INIT = ROOT / "scripts" / "postgres-init.sql"
MIGRATIONS_DIR = ROOT / "services" / "agent-orchestrator-svc" / "migrations"


def dsn() -> str:
    direct = os.getenv("DOCUMIND_POSTGRES_DSN")
    if direct:
        return direct
    host = os.getenv("DOCUMIND_PG_HOST", "localhost")
    port = os.getenv("DOCUMIND_PG_PORT", "5432")
    db = os.getenv("DOCUMIND_PG_DB", "documind")
    user = os.getenv("DOCUMIND_PG_USER", "documind")
    pw = os.getenv("DOCUMIND_PG_PASSWORD", "documind")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def _sanitize_psql_sql(sql: str) -> str:
    lines: list[str] = []
    for line in sql.splitlines():
        if line.lstrip().startswith("\\"):
            continue
        lines.append(line)
    return "\n".join(lines)


async def ensure_migration_tracker() -> None:
    conn = await asyncpg.connect(dsn())
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = '_migrations')",
        )
        if exists:
            print("[agent-orchestrator] migration tracker already present")
            return

        sql = _sanitize_psql_sql(POSTGRES_INIT.read_text(encoding="utf-8"))
        await conn.execute(sql)
        print("[agent-orchestrator] postgres-init applied")
    finally:
        await conn.close()


async def main() -> None:
    await ensure_migration_tracker()
    await apply_migrations(MIGRATIONS_DIR, "agent-orchestrator")
    print("[agent-orchestrator] bootstrap complete")


if __name__ == "__main__":
    asyncio.run(main())
