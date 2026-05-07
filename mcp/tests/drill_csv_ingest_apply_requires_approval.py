#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 3. NEGATIVE: apply without approval is denied."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_csv_ingest as s  # noqa: E402


TENANT = "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a"


def _csv() -> str:
    path = Path("/tmp/csv-ingest-approval-required.csv")
    path.write_text("id,name\n1,Ada\n", encoding="utf-8")
    return str(path)


def main() -> int:
    s.state.plans.clear()
    s.state.approvals.clear()
    plan = s._propose_load({
        "path": _csv(),
        "target_table": "csv_ingest_demo",
        "tenant_id": TENANT,
        "column_mapping": {"id": "id", "name": "name"},
    }, TENANT)["result"]["plan"]
    try:
        s._apply_approved_load({"draft_id": plan["draft_id"], "tenant_id": TENANT}, TENANT)
    except HTTPException as exc:
        if exc.status_code == 403 and exc.detail.get("code") == "approval_required":
            print("ALL CSV-INGEST APPLY-REQUIRES-APPROVAL STEPS PASSED")
            return 0
        print(f"FAIL: wrong denial: {exc.status_code} {exc.detail}")
        return 1
    print("FAIL: apply succeeded without approval")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
