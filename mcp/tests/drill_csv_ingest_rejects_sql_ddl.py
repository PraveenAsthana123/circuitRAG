#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 6: raw SQL and DDL are rejected before DB access."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_csv_ingest as s  # noqa: E402


TENANT = "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a"


def main() -> int:
    path = Path("/tmp/csv-ingest-reject-sql.csv")
    path.write_text("id,name\n1,Ada\n", encoding="utf-8")
    bad_cases = [
        {"sql": "INSERT INTO csv_ingest_demo VALUES (1)"},
        {"target_table": "DROP TABLE csv_ingest_demo"},
        {"column_mapping": {"id": "id", "name": "name; DELETE FROM x"}},
    ]
    for bad in bad_cases:
        args = {
            "path": str(path),
            "target_table": "csv_ingest_demo",
            "tenant_id": TENANT,
            "column_mapping": {"id": "id", "name": "name"},
        }
        args.update(bad)
        try:
            s._propose_load(args, TENANT)
        except HTTPException as exc:
            if exc.status_code in (400, 403):
                continue
            print(f"FAIL: wrong status for {bad}: {exc.status_code}")
            return 1
        print(f"FAIL: accepted SQL/DDL case: {bad}")
        return 1
    print("ALL CSV-INGEST REJECTS-SQL-DDL STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
