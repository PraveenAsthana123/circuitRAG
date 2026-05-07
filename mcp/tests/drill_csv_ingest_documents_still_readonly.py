#!/usr/bin/env python3
# RESOURCES: readonly
# ruff: noqa: E402,I001
"""ADR-028 guardrail 1. NEGATIVE: documents server still has zero write tools."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import server_documents  # noqa: E402


def main() -> int:
    tools = server_documents.TOOLS
    names = {t["name"] for t in tools}
    if "documents.csv_parse" not in names:
        print("FAIL: documents.csv_parse missing")
        return 1
    write_tools = [t["name"] for t in tools if t.get("side_effects") == "write"]
    if write_tools:
        print(f"FAIL: documents server has write tools: {write_tools}")
        return 1
    if any("csv_ingest" in name for name in names):
        print("FAIL: csv_ingest namespace leaked into documents server")
        return 1
    print("ALL CSV-INGEST DOCUMENTS-READONLY STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
