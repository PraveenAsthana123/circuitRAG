#!/usr/bin/env python3
# RESOURCES: frontend
"""
Drill: the operator dashboard keeps the Agentic control plane summary
panel wired into the main admin page.

Static source-contract drill. It locks the operator-visible summary
surface without requiring a running frontend server.

Six steps. Five negative assertions.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADMIN_PAGE = REPO / "services" / "frontend" / "app" / "admin" / "page.tsx"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def main() -> None:
    # NEGATIVE: agentic summary surface stays wired into admin page;
    # missing header / metrics / approvals table / latest sections /
    # control-plane CTA = operator regression we lock against.
    step("1. admin page file exists")
    if not ADMIN_PAGE.exists():
        fail(f"missing admin page file: {ADMIN_PAGE}")
    text = ADMIN_PAGE.read_text(encoding="utf-8")
    ok("admin page file present")

    step("2. summary panel header is present")
    if "Agentic control plane summary" not in text:
        fail("missing 'Agentic control plane summary' header")
    if "Projects, pending approvals, recent human decisions, and distilled memory highlights." not in text:
        fail("missing agentic summary panel helper copy")
    ok("summary panel header + helper copy present")

    step("3. top-level summary metrics are present")
    metrics = [
        "Projects",
        "Tracked tasks",
        "Pending approvals",
        "Recent memories",
    ]
    missing = [metric for metric in metrics if metric not in text]
    if missing:
        fail(f"missing summary metric label(s): {missing}")
    ok(f"all {len(metrics)} summary metric labels present")

    step("4. pending approvals table is still present")
    table_markers = [
        "No pending approvals.",
        "<th>Task</th>",
        "<th>Status</th>",
        "<th>Risk</th>",
        "<th>Goal</th>",
    ]
    missing = [marker for marker in table_markers if marker not in text]
    if missing:
        fail(f"missing pending-approval table marker(s): {missing}")
    ok("pending approvals table structure present")

    step("5. latest approvals + memories sections are present")
    section_markers = [
        "Latest approval decisions",
        "Latest memories",
        "No recent approvals yet.",
        "No recent memories yet.",
    ]
    missing = [marker for marker in section_markers if marker not in text]
    if missing:
        fail(f"missing approvals/memories section marker(s): {missing}")
    ok("latest approvals + latest memories sections present")

    step("6. control-plane CTA is present")
    cta_markers = [
        "Open control plane",
        "/admin/agentic/control-plane",
    ]
    missing = [marker for marker in cta_markers if marker not in text]
    if missing:
        fail(f"missing control-plane CTA marker(s): {missing}")
    ok("dashboard summary links into control plane")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 ADMIN-AGENTIC-SUMMARY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
