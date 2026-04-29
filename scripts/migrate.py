#!/usr/bin/env python3
"""
Migration runner — applies numbered SQL files per service.

Usage::

    python scripts/migrate.py services/ingestion-svc/migrations ingestion

Tracks applied migrations in ``public._migrations`` (created by
``scripts/postgres-init.sql``). Idempotent: re-running is safe.
"""
from __future__ import annotations

import asyncio
import argparse
import hashlib
import os
import sys
from pathlib import Path

import asyncpg


def dsn() -> str:
    host = os.getenv("DOCUMIND_PG_HOST", "localhost")
    port = os.getenv("DOCUMIND_PG_PORT", "5432")
    db = os.getenv("DOCUMIND_PG_DB", "documind")
    user = os.getenv("DOCUMIND_PG_USER", "documind")
    pw = os.getenv("DOCUMIND_PG_PASSWORD", "documind")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


async def apply(migrations_dir: Path, service: str) -> None:
    files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    if not files:
        print(f"[{service}] no migrations in {migrations_dir}")
        return

    conn = await asyncpg.connect(dsn())
    try:
        rows = await conn.fetch(
            "SELECT filename FROM public._migrations WHERE service = $1",
            service,
        )
        applied = {r["filename"] for r in rows}

        for f in files:
            if f.name in applied:
                print(f"[{service}] skip  {f.name}")
                continue
            sql = f.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO public._migrations (service, filename, checksum) "
                    "VALUES ($1, $2, $3)",
                    service, f.name, checksum,
                )
            print(f"[{service}] apply {f.name} ok")
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply numbered SQL migrations for one service and record "
            "applied filenames in public._migrations."
        )
    )
    parser.add_argument("migrations_dir", help="directory containing *.sql migration files")
    parser.add_argument("service", help="service name recorded in public._migrations")
    args = parser.parse_args()
    migrations_dir = Path(args.migrations_dir).resolve()
    service = args.service
    if not migrations_dir.is_dir():
        print(f"Not a directory: {migrations_dir}")
        return 2
    asyncio.run(apply(migrations_dir, service))
    return 0


if __name__ == "__main__":
    sys.exit(main())
