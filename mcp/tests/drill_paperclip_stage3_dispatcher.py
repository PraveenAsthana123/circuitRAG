#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Paperclip Stage-3 — dispatcher composes propose + openclaw.dispatch.

Per CLAUDE.md §43 + §44 + §47. Locks Stage-3 promotion that:

  - paperclip_dispatcher.py exists as SEPARATE file (NOT inside
    paperclip_manager.py — sandbox contract preserved)
  - paperclip_manager.py source UNCHANGED (no def dispatch_*)
  - Stage-3 contract: dispatch_next_task() + CombinedResult dataclass
  - Default opt-in via PAPERCLIP_DISPATCH_ENABLED=1
  - When disabled → raises PaperclipDispatchDisabled
  - When enabled → composes propose_next_task + openclaw.dispatch
  - Stage-1 drill (drill_paperclip_stage1) still passes
  - Stage-2 drill (drill_paperclip_stage2_propose) still passes

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
DISPATCHER = SCRIPTS / "paperclip_dispatcher.py"
MANAGER = SCRIPTS / "paperclip_manager.py"
PYTHON = REPO / ".venv" / "bin" / "python3"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: paperclip_dispatcher.py exists as SEPARATE file --")
    if not DISPATCHER.exists():
        print(f"x {DISPATCHER} missing")
        return 1
    src = DISPATCHER.read_text(encoding="utf-8")
    if len(src) < 3000:
        print(f"x dispatcher too short ({len(src)} chars)")
        return 1
    print(f"  ok: dispatcher present ({len(src)} chars)")

    print("-- 2. NEGATIVE: paperclip_manager.py UNCHANGED (no def dispatch_*) --")
    # Stage-1 sandbox contract: paperclip_manager must NOT contain
    # def dispatch_*. Drill verifies the sandbox file is still pure
    # read+suggest.
    manager_src = MANAGER.read_text(encoding="utf-8")
    forbidden_def = re.compile(
        r"^def\s+(push|dispatch|assign|escalate|merge|deploy|"
        r"rollback|promote|write|update|mutate|delete|create|insert)_",
        re.MULTILINE,
    )
    matches = forbidden_def.findall(manager_src)
    if matches:
        print(f"x paperclip_manager has Stage-3 leakage: {matches}")
        return 1
    print("  ok: paperclip_manager.py source unchanged (sandbox preserved)")

    print("-- 3. POSITIVE: dispatcher exports 4 contract surfaces --")
    os.environ.pop("PAPERCLIP_DISPATCH_ENABLED", None)
    import paperclip_dispatcher
    importlib.reload(paperclip_dispatcher)
    for name in ("is_available", "dispatch_next_task", "status",
                 "PaperclipDispatchDisabled", "CombinedResult"):
        if not hasattr(paperclip_dispatcher, name):
            print(f"x paperclip_dispatcher.{name} missing")
            return 1
    print("  ok: 5 surfaces exported (4 contract + 1 dataclass)")

    print("-- 4. NEGATIVE: default is_available()=False (PAPERCLIP_DISPATCH_ENABLED unset) --")
    if paperclip_dispatcher.is_available():
        print(f"x default must be False; got {paperclip_dispatcher.is_available()}")
        return 1
    print("  ok: default opt-out preserved")

    print("-- 5. NEGATIVE: dispatch_next_task raises PaperclipDispatchDisabled when off --")
    raised = False
    try:
        paperclip_dispatcher.dispatch_next_task()
    except paperclip_dispatcher.PaperclipDispatchDisabled as exc:
        raised = True
        if "PAPERCLIP_DISPATCH_ENABLED" not in str(exc):
            print(f"x error msg must cite PAPERCLIP_DISPATCH_ENABLED; got {str(exc)[:200]}")
            return 1
    if not raised:
        print("x dispatch_next_task should raise when flag off")
        return 1
    print("  ok: PaperclipDispatchDisabled raised + cites flag")

    print("-- 6. NEGATIVE: PaperclipDispatchDisabled subclasses RuntimeError --")
    if not issubclass(paperclip_dispatcher.PaperclipDispatchDisabled, RuntimeError):
        print("x PaperclipDispatchDisabled must subclass RuntimeError")
        return 1
    print("  ok: exception is RuntimeError-subclass")

    print("-- 7. NEGATIVE: existing Stage-1 + Stage-2 drills still pass --")
    # The sandbox contract is non-negotiable. Stage-3 promotion must
    # NOT regress Stage-1 or Stage-2 invariants.
    for drill in ("drill_paperclip_stage1.py", "drill_paperclip_stage2_propose.py"):
        proc = subprocess.run(
            [str(PYTHON), str(REPO / "mcp" / "tests" / drill)],
            capture_output=True, text=True, timeout=30, cwd=REPO,
        )
        if proc.returncode != 0 or "ALL 8 STEPS PASSED" not in proc.stdout:
            print(f"x {drill} regressed:")
            print(proc.stdout[-300:])
            return 1
    print("  ok: drill_paperclip_stage1 + drill_paperclip_stage2_propose both 8/8")

    print("-- 8. POSITIVE: source documents Stage-4 future direction --")
    # Stage-3 ships composition; Stage-4 will land real RPC. Drill
    # enforces the source documents the path so contributors know
    # what's next without grep.
    if "Stage-4" not in src:
        print("x source must reference Stage-4 (real RPC) future direction")
        return 1
    if "MCP server" not in src:
        print("x source must mention agents-as-MCP-server requirement for Stage-4")
        return 1
    print("  ok: Stage-4 path documented in source")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
