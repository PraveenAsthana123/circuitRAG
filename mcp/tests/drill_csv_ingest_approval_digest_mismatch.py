#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 4. NEGATIVE: changing CSV after approval blocks apply."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_csv_ingest as s  # noqa: E402


TENANT = "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a"


def main() -> int:
    os.environ["CSV_INGEST_OPERATOR_APPROVAL_TOKEN"] = "drill-token"
    s.state.plans.clear()
    s.state.approvals.clear()
    path = Path("/tmp/csv-ingest-digest-mismatch.csv")
    path.write_text("id,name\n1,Ada\n", encoding="utf-8")
    plan = s._propose_load({
        "path": str(path),
        "target_table": "csv_ingest_demo",
        "tenant_id": TENANT,
        "column_mapping": {"id": "id", "name": "name"},
    }, TENANT)["result"]["plan"]
    s._submit_for_approval({
        "draft_id": plan["draft_id"],
        "approval_token": "drill-token",
        "approved_by": "drill",
    }, TENANT)
    path.write_text("id,name\n1,Ada\n2,Grace\n", encoding="utf-8")
    try:
        s._apply_approved_load({"draft_id": plan["draft_id"], "tenant_id": TENANT}, TENANT)
    except HTTPException as exc:
        if exc.status_code == 409 and exc.detail.get("code") == "approval_digest_mismatch":
            print("ALL CSV-INGEST APPROVAL-DIGEST-MISMATCH STEPS PASSED")
            return 0
        print(f"FAIL: wrong mismatch result: {exc.status_code} {exc.detail}")
        return 1
    print("FAIL: apply succeeded after CSV changed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
