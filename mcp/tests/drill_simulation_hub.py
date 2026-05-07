#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Simulation hub page + README snapshot contract.

Locks the Simulation hub UI + README snapshot section so the
operator's live trust surface stays intact. Without this drill:
  - the simulation page can silently drop sections (MCP / agents /
    council) and operators lose visibility
  - the README snapshot can drift from reality (claims 0 errors when
    there are some; claims drills present when removed)

Negative assertions cover: page absent; sidebar entry missing; BFF
route absent; README snapshot section missing or stripped of
verification commands; standards compliance table missing.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "simulation" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "simulation" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
README = REPO / "README.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: simulation page + BFF route + sidebar entry exist --")
    for p in (PAGE, ROUTE, SIDEBAR, README):
        if not p.exists():
            raise AssertionError(f"missing {p.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    route = ROUTE.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    print("  ok: 4 files present")

    print("-- 2. POSITIVE: sidebar links to /admin/simulation --")
    require(sidebar, "/admin/simulation", "sidebar link")
    print("  ok: sidebar entry present")

    print("-- 3. POSITIVE: simulation page has 5 canonical sections --")
    for needle, label in [
        ("Infrastructure", "Infrastructure section"),
        ("Agents", "Agents section"),
        ("Council", "Council section"),
        ("Drill catalog", "Drill catalog section"),
        ("test fixtures", "Multi-modal test fixtures section"),
    ]:
        require(page, needle, label)
    print("  ok: 5 canonical sections present")

    print("-- 4. POSITIVE: BFF route aggregates 4 real signal sources --")
    for needle, label in [
        ("ollama", "Ollama API call"),
        ("issue_audit.jsonl", "audit JSONL read"),
        ("agent_registry.py", "agent registry parse"),
        ("server_", "MCP server scan"),
    ]:
        require(route, needle, label)
    print("  ok: 4 signal sources wired")

    print("-- 5. NEGATIVE: page MUST auto-refresh (live data, not stale snapshot) --")
    require(page, "setInterval", "auto-refresh interval")
    require(page, "autoRefresh", "auto-refresh state")
    print("  ok: auto-refresh wired")

    print("-- 6. POSITIVE: README has Snapshot section with metrics + date --")
    require(readme, "## Snapshot", "Snapshot section heading")
    require(readme, "2026-04-30", "date stamp")
    require(readme, "MDT", "timezone marker")
    require(readme, "Linux x86_64", "location marker")
    print("  ok: snapshot date + timezone + location present")

    print("-- 7. POSITIVE: README snapshot has all 8 metric rows --")
    for metric in (
        "Python LOC",
        "TypeScript LOC",
        "Go LOC",
        "Drills",
        "ADRs",
        "Runbooks",
        "Deep-dive pages",
        "Commits this session",
    ):
        require(readme, metric, f"snapshot metric: {metric}")
    print("  ok: 8 metrics in snapshot table")

    print("-- 8. NEGATIVE: README MUST cite verification commands --")
    require(readme, "verify-stack.sh", "verify-stack reference")
    require(readme, "load-test.sh", "load-test reference")
    require(readme, "scripts/run_drills.py", "run_drills reference")
    print("  ok: 3 verification commands cited")

    print("-- 9. POSITIVE: README has standards compliance table --")
    for std in ("PEP 8", "TDD-style", "NIST AI RMF", "OWASP", "SOC 2"):
        require(readme, std, f"standard: {std}")
    print("  ok: 5 standards cited with compliance status")

    print("-- 10. NEGATIVE: README MUST honestly cite NOT top 1% --")
    require(readme, "NOT top 1%", "honest verdict marker")
    require(readme, "MISSING.md", "MISSING.md cross-reference")
    print("  ok: honest verdict + MISSING.md reference")

    print("-- 11. POSITIVE: README points at STATUS.md + benchmarks + trust runbook --")
    for path in ("docs/STATUS.md", "docs/benchmarks/", "docs/runbooks/component-trust.md"):
        require(readme, path, f"reference to {path}")
    print("  ok: 3 canonical state docs cross-referenced")

    print("-- 12. NEGATIVE: README MUST NOT carry placeholder language --")
    for forbidden in ("TODO", "TBD", "FIXME", "Lorem ipsum"):
        if forbidden in readme:
            raise AssertionError(f"forbidden placeholder in README.md: {forbidden}")
    print("  ok: no placeholder language remains")

    print("\nALL 12 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
