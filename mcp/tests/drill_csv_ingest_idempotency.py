#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 5: duplicate Idempotency-Key returns original response."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_csv_ingest as s  # noqa: E402


TENANT = "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a"


def main() -> int:
    path = Path("/tmp/csv-ingest-idempotency.csv")
    path.write_text("id,name\n1,Ada\n", encoding="utf-8")
    body = {
        "name": "csv_ingest.propose_load",
        "tenant_id": TENANT,
        "arguments": {
            "path": str(path),
            "target_table": "csv_ingest_demo",
            "tenant_id": TENANT,
            "column_mapping": {"id": "id", "name": "name"},
        },
    }
    client = TestClient(s.app)
    headers = {"Idempotency-Key": "csv-ingest-drill-key"}
    first = client.post("/tools/call", json=body, headers=headers)
    second = client.post("/tools/call", json=body, headers=headers)
    if first.status_code != 200 or second.status_code != 200:
        print(f"FAIL: unexpected status codes {first.status_code}, {second.status_code}")
        return 1
    first_body = first.json()
    second_body = second.json()
    if first_body != {k: v for k, v in second_body.items() if k != "idempotent_replay"}:
        print("FAIL: duplicate idempotency key did not replay original response")
        return 1
    if second_body.get("idempotent_replay") is not True:
        print("FAIL: replay response missing idempotent_replay marker")
        return 1
    print("ALL CSV-INGEST IDEMPOTENCY STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
