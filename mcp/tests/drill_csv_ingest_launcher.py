#!/usr/bin/env python3
# RESOURCES: readonly
"""ADR-028 guardrail 8. NEGATIVE: launcher honors MCP_CSV_INGEST_PORT and uses no sudo."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "scripts" / "start_mcp_csv_ingest.sh"


def main() -> int:
    src = LAUNCHER.read_text(encoding="utf-8")
    if "${MCP_CSV_INGEST_PORT:-8095}" not in src:
        print("FAIL: launcher missing env override pattern")
        return 1
    if "mcp.server_csv_ingest:app" not in src:
        print("FAIL: launcher does not target mcp.server_csv_ingest:app")
        return 1
    sudo_lines = [ln for ln in src.splitlines() if "sudo " in ln and not ln.strip().startswith("#")]
    if sudo_lines:
        print(f"FAIL: launcher uses sudo: {sudo_lines}")
        return 1
    print("ALL CSV-INGEST LAUNCHER STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
