#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 2: CSV ingest catalog has 5 tools; only apply writes."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_csv_ingest  # noqa: E402


EXPECTED = {
    "csv_ingest.propose_load",
    "csv_ingest.validate_load",
    "csv_ingest.submit_for_approval",
    "csv_ingest.apply_approved_load",
    "csv_ingest.load_status",
}


def main() -> int:
    tools = server_csv_ingest.TOOLS
    names = {t["name"] for t in tools}
    if names != EXPECTED:
        print(f"FAIL: tool catalog mismatch: {sorted(names)}")
        return 1
    write_tools = {t["name"] for t in tools if t.get("side_effects") == "write"}
    if write_tools != {"csv_ingest.apply_approved_load"}:
        print(f"FAIL: only apply may be write; got {sorted(write_tools)}")
        return 1
    for tool in tools:
        if not tool.get("required_scopes"):
            print(f"FAIL: missing required_scopes: {tool['name']}")
            return 1
    print("ALL CSV-INGEST TOOL-CATALOG STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
