#!/usr/bin/env python3
# RESOURCES: frontend
"""
Drill: the Agentic Control Plane UI is wired in source.

This is a static source-contract drill rather than a live HTTP drill.
It avoids depending on a running Next.js dev server while still
locking the load-bearing UI integration points:

  * the control-plane page file exists
  * the page contains the expected section headers
  * the page contains the jump links / anchor ids
  * the page contains project/task selector scaffolding
  * the sidebar contains the control-plane route
  * the existing agentic page links into the control plane

Six steps. Five negative assertions.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTROL_PLANE = REPO / "services" / "frontend" / "app" / "admin" / "agentic" / "control-plane" / "page.tsx"
AGENTIC_PAGE = REPO / "services" / "frontend" / "app" / "admin" / "agentic" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def main() -> None:
    # NEGATIVE: control-plane UI page renders required structure.
    # Per-step assertions below verify each contract.
    step("1. control-plane page file exists")
    if not CONTROL_PLANE.exists():
        fail(f"missing page file: {CONTROL_PLANE}")
    body = CONTROL_PLANE.read_text(encoding="utf-8")
    ok("control-plane page file present")

    step("2. expected control-plane section headers exist in source")
    headings = [
        "Agentic control plane",
        "Role routing and policy",
        "Project graph",
        "Task execution trail",
    ]
    missing = [heading for heading in headings if heading not in body]
    if missing:
        fail(f"missing heading(s): {missing}")
    ok(f"all {len(headings)} section headings present")

    step("3. jump links and anchor ids are wired")
    markers = [
        'href="#role-routing-policy"',
        'href="#project-graph"',
        'href="#task-execution-trail"',
        'id="role-routing-policy"',
        'id="project-graph"',
        'id="task-execution-trail"',
        "Jump to each surface",
    ]
    missing = [marker for marker in markers if marker not in body]
    if missing:
        fail(f"missing jump-link/anchor marker(s): {missing}")
    ok("jump links and section anchors are wired")

    step("4. project/task selector scaffolding is present")
    selector_markers = [
        "agentic-project-select",
        "agentic-task-select",
        "Select a project",
        "Select a task",
        "Project memories",
        "Task memories",
    ]
    missing = [marker for marker in selector_markers if marker not in body]
    if missing:
        fail(f"missing selector/detail marker(s): {missing}")
    ok("project/task selectors and detail regions are present")

    step("5. sidebar exposes the control-plane route")
    sidebar_text = SIDEBAR.read_text(encoding="utf-8")
    sidebar_markers = [
        "/admin/agentic",
        "/admin/agentic/control-plane",
        "Agentic tasks",
        "Agentic control plane",
    ]
    missing = [marker for marker in sidebar_markers if marker not in sidebar_text]
    if missing:
        fail(f"missing sidebar marker(s): {missing}")
    ok("sidebar contains both agentic routes")

    step("6. existing agentic page links into control plane")
    agentic_text = AGENTIC_PAGE.read_text(encoding="utf-8")
    link_markers = [
        "Open control plane",
        "/admin/agentic/control-plane",
    ]
    missing = [marker for marker in link_markers if marker not in agentic_text]
    if missing:
        fail(f"missing agentic-page control-plane link marker(s): {missing}")
    ok("Agentic tasks page links into control plane")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 AGENTIC-CONTROL-PLANE UI STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
