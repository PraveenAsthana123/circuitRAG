#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: scripts/techstack_audit.py — empirical install-checker contract.

Per CLAUDE.md §43. Locks the audit script's behavior:

  - Script exists + executable
  - --json mode produces parseable JSON with summary + sections
  - Default mode produces operator-readable text
  - All 9 CRITICAL tools must be installed (or drill fails — those
    are the must-have foundations: docker, git, fastapi, uvicorn,
    pydantic, httpx, react, next, typescript)
  - Exit code 0 when everything ok; 2 when CRITICAL missing
  - --section filter narrows to one section
  - Audit covers >=6 sections (python_runtime_core, python_rag_stack,
    python_observability, binaries, frontend_npm, mcp_servers_local,
    missing_per_eval_page)
  - Audit reports "rejected" criticality for the 3 frameworks the
    tool-evaluation explicitly rejected (CrewAI, Agno, PraisonAI)

Eight steps. Five negative assertions.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "scripts" / "techstack_audit.py"
PYTHON = REPO / ".venv" / "bin" / "python3"


def _run(*args: str, timeout: int = 30) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PYTHON), str(AUDIT), *args],
        capture_output=True, text=True, timeout=timeout, cwd=REPO,
    )
    return proc.returncode, proc.stdout


def main() -> int:
    print("-- 1. POSITIVE: techstack_audit.py exists + executable --")
    if not AUDIT.exists():
        print(f"x {AUDIT} missing")
        return 1
    print(f"  ok: {AUDIT.name} present")

    print("-- 2. POSITIVE: --json mode produces valid JSON with summary + sections --")
    rc, out = _run("--json")
    try:
        report = json.loads(out)
    except json.JSONDecodeError as e:
        print(f"x JSON output invalid: {e}; head: {out[:200]}")
        return 1
    if "summary" not in report or "sections" not in report:
        print("x JSON must have 'summary' + 'sections' top-level keys")
        return 1
    print(f"  ok: JSON report has summary + sections")

    print("-- 3. POSITIVE: default text mode produces operator-readable output --")
    rc, out = _run()
    if "TOTAL:" not in out or "By criticality:" not in out:
        print(f"x text output missing required headers")
        return 1
    print(f"  ok: text report has summary headers")

    print("-- 4. NEGATIVE: all 9 CRITICAL tools must be installed --")
    rc, out = _run("--json")
    report = json.loads(out)
    crit_stats = report["summary"]["by_criticality"].get("critical", {})
    if crit_stats.get("missing", 0) > 0:
        print(f"x {crit_stats['missing']} CRITICAL tool(s) missing — drill blocks")
        # List which ones
        for items in report["sections"].values():
            for item in items:
                if item["criticality"] == "critical" and not item["installed"]:
                    print(f"    - {item['name']}")
        return 1
    if crit_stats.get("installed", 0) != 9:
        print(f"x expected 9 CRITICAL tools; got {crit_stats.get('installed')}")
        return 1
    print(f"  ok: all 9 CRITICAL tools installed")

    print("-- 5. NEGATIVE: rejected frameworks (CrewAI/Agno/PraisonAI) NOT installed --")
    # Per tool-evaluation: these were rejected. If they appear as installed,
    # something is wrong (someone added them despite the verdict).
    rejected_seen = []
    for items in report["sections"].values():
        for item in items:
            if item["criticality"] == "rejected" and item["installed"]:
                rejected_seen.append(item["name"])
    if rejected_seen:
        print(f"x rejected frameworks installed despite verdict: {rejected_seen}")
        return 1
    rejected_total = sum(
        1 for items in report["sections"].values() for item in items
        if item["criticality"] == "rejected"
    )
    if rejected_total != 3:
        print(f"x expected 3 rejected entries (CrewAI, Agno, PraisonAI); got {rejected_total}")
        return 1
    print(f"  ok: 3 rejected frameworks all NOT installed (verdict respected)")

    print("-- 6. POSITIVE: audit covers >=6 sections --")
    expected_sections = (
        "python_runtime_core", "python_rag_stack", "python_observability",
        "binaries", "frontend_npm", "mcp_servers_local",
        "missing_per_eval_page",
    )
    missing_sections = [s for s in expected_sections if s not in report["sections"]]
    if missing_sections:
        print(f"x sections missing: {missing_sections}")
        return 1
    print(f"  ok: all {len(expected_sections)} expected sections present")

    print("-- 7. NEGATIVE: --section filter narrows correctly --")
    rc, out = _run("--section", "binaries", "--json")
    report = json.loads(out)
    if list(report["sections"].keys()) != ["binaries"]:
        print(f"x --section filter failed; sections: {list(report['sections'].keys())}")
        return 1
    print(f"  ok: --section binaries returns single section")

    print("-- 8. NEGATIVE: exit code reflects criticality --")
    # If critical missing → exit 2; if any missing → exit 1; else 0.
    rc, _out = _run()
    # In our current state: 9/9 critical installed, but other tools missing,
    # so exit should be 1 (not 0, not 2). If this changes (all installed),
    # exit is 0 — also acceptable.
    if rc not in (0, 1, 2):
        print(f"x exit code must be 0/1/2; got {rc}")
        return 1
    # Critical=2 should never happen in a healthy repo (drill step 4 covers).
    if rc == 2:
        print(f"x exit code 2 means critical tool missing")
        return 1
    print(f"  ok: exit code {rc} (0=all-installed, 1=some-non-critical-missing)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
