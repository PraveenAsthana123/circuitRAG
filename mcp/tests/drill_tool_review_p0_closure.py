#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: listed tool-review P0 blockers stay closed.

NEGATIVE: any reopened P0 in the listed reviews fails the closure subset.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REVIEWS = {
    "circuit-breaker": REPO / "docs" / "architecture" / "tool-reviews" / "circuit-breaker.md",
    "mcp-server-deploy": REPO / "docs" / "architecture" / "tool-reviews" / "mcp-server-deploy.md",
    "mcp-server-observe": REPO / "docs" / "architecture" / "tool-reviews" / "mcp-server-observe.md",
    "mcp-server-research": REPO / "docs" / "architecture" / "tool-reviews" / "mcp-server-research.md",
    "mcp-server-tests": REPO / "docs" / "architecture" / "tool-reviews" / "mcp-server-tests.md",
}
SERVERS = {
    "mcp-server-deploy": REPO / "mcp" / "server_deploy.py",
    "mcp-server-observe": REPO / "mcp" / "server_observe.py",
    "mcp-server-research": REPO / "mcp" / "server_research.py",
    "mcp-server-tests": REPO / "mcp" / "server_tests.py",
}


def main() -> int:
    print("-- 1. POSITIVE: listed review files exist --")
    missing = [name for name, path in REVIEWS.items() if not path.exists()]
    if missing:
        print(f"x missing review files: {missing}")
        return 1
    print("  ok: all listed reviews present")

    print("-- 2. NEGATIVE: every listed review has P0 count 0 --")
    for name, path in REVIEWS.items():
        text = path.read_text(encoding="utf-8")
        if not re.search(r"\|\s*P0[^|]*\|\s*0\s*\|", text):
            print(f"x {name} review does not report P0=0")
            return 1
    print("  ok: listed reviews report P0=0")

    print("-- 3. POSITIVE: MCP servers call setup_server_otel with stable service names --")
    for name, path in SERVERS.items():
        text = path.read_text(encoding="utf-8")
        if "setup_server_otel(app" not in text:
            print(f"x {name} missing setup_server_otel(app)")
            return 1
        if f'service_name="{name}"' not in text:
            print(f"x {name} missing service_name={name!r}")
            return 1
    print("  ok: all four MCP servers wire OTel")

    print("-- 4. POSITIVE: MCP servers mount /metrics endpoint --")
    for name, path in SERVERS.items():
        text = path.read_text(encoding="utf-8")
        if "mount_metrics_endpoint(app)" not in text:
            print(f"x {name} missing mount_metrics_endpoint(app)")
            return 1
    print("  ok: all four MCP servers mount metrics")

    print("-- 5. NEGATIVE: research server no longer has broad except Exception --")
    research = SERVERS["mcp-server-research"].read_text(encoding="utf-8")
    if "except Exception" in research:
        print("x mcp-server-research still contains broad except Exception")
        return 1
    print("  ok: research exception scope narrowed")

    print("-- 6. POSITIVE: README carries P0 closure update --")
    readme = (REPO / "docs" / "architecture" / "tool-reviews" / "README.md").read_text(encoding="utf-8")
    if "P0 closure update" not in readme or "mcp-server-research" not in readme:
        print("x tool-review README missing closure update")
        return 1
    print("  ok: README documents closure subset")

    print("\nALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
