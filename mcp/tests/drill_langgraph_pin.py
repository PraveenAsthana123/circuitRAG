#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: agent-orchestrator LangGraph dependency pins.

The orchestrator service now treats `langgraph` and
`langchain-core` as reproducibility-sensitive dependencies. A
floating minor range here permits subtle planner/runtime behavior
changes without a code diff in this repo.

Five steps. Three negative assertions.

  1. POSITIVE: orchestrator requirements file exists.
  2. NEGATIVE: `langgraph` is pinned with `==`, not a range.
  3. NEGATIVE: `langchain-core` is pinned with `==`, not a range.
  4. NEGATIVE: requirements comment mentions the drill by name,
     so the contract is discoverable at the edit site.
  5. POSITIVE: emit the pinned versions.

Run: python3 mcp/tests/drill_langgraph_pin.py
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
REQ = REPO / "services" / "agent-orchestrator-svc" / "requirements.txt"


def fail(msg: str) -> None:
    print(f"  x {msg}")
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"  ok: {msg}")


def step(title: str) -> None:
    print(f"\n-- {title} --")


def _extract_pin(text: str, pkg: str) -> str | None:
    m = re.search(rf"^{re.escape(pkg)}==([^\s]+)$", text, re.MULTILINE)
    return m.group(1) if m else None


def main() -> int:
    step("1. POSITIVE: orchestrator requirements file exists")
    if not REQ.exists():
        fail(f"missing requirements file: {REQ}")
    text = REQ.read_text(encoding="utf-8")
    ok(str(REQ.relative_to(REPO)))

    step("2. NEGATIVE: langgraph is pinned with ==")
    langgraph_ver = _extract_pin(text, "langgraph")
    if not langgraph_ver:
        fail("langgraph is not pinned with ==")
    ok(f"langgraph=={langgraph_ver}")

    step("3. NEGATIVE: langchain-core is pinned with ==")
    langchain_core_ver = _extract_pin(text, "langchain-core")
    if not langchain_core_ver:
        fail("langchain-core is not pinned with ==")
    ok(f"langchain-core=={langchain_core_ver}")

    step("4. NEGATIVE: requirements comment mentions drill_langgraph_pin")
    if "drill_langgraph_pin" not in text:
        fail("requirements comment no longer references drill_langgraph_pin")
    ok("requirements comment references drill_langgraph_pin")

    step("5. POSITIVE: emit pinned versions")
    ok(f"pins: langgraph={langgraph_ver}, langchain-core={langchain_core_ver}")

    print("\nALL 5 LANGGRAPH-PIN STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
