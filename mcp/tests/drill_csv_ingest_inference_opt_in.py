#!/usr/bin/env python3
# RESOURCES: readonly
"""ADR-028 guardrail 9. NEGATIVE: inference connects only when env URL is set."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"


def main() -> int:
    src = MAIN.read_text(encoding="utf-8")
    if "DOCUMIND_MCP_CSV_INGEST_URL" not in src:
        print("FAIL: inference-svc missing CSV ingest env hook")
        return 1
    if not re.search(r'\(\s*"csv_ingest"\s*,\s*os\.getenv\("DOCUMIND_MCP_CSV_INGEST_URL",\s*""\)', src):
        print("FAIL: CSV ingest MCP hook is not default-empty opt-in")
        return 1
    if "ADR-028" not in src:
        print("FAIL: inference-svc comment does not cite ADR-028 provenance")
        return 1
    print("ALL CSV-INGEST INFERENCE-OPT-IN STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
