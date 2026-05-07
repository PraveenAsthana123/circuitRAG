#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 7. NEGATIVE: tenant mismatch is rejected before DB access."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_csv_ingest as s  # noqa: E402


def main() -> int:
    s.state.plans.clear()
    path = Path("/tmp/csv-ingest-tenant-mismatch.csv")
    path.write_text("id,name\n1,Ada\n", encoding="utf-8")
    try:
        s._propose_load({
            "path": str(path),
            "target_table": "csv_ingest_demo",
            "tenant_id": "tenant-b",
            "column_mapping": {"id": "id", "name": "name"},
        }, "tenant-a")
    except HTTPException as exc:
        if exc.status_code == 403 and exc.detail.get("code") == "tenant_mismatch" and not s.state.plans:
            print("ALL CSV-INGEST TENANT-MISMATCH STEPS PASSED")
            return 0
        print(f"FAIL: wrong tenant denial: {exc.status_code} {exc.detail}")
        return 1
    print("FAIL: tenant mismatch accepted")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
