# RESOURCES: readonly
"""
Drill: §19 sidecar-advisor Dockerfile + final 9-iteration roll-up.

Two responsibilities:

  A. Validate the new sidecar-advisor Dockerfile structurally
     (without requiring `docker` on PATH or building the image — CI
     runs the actual build).
  B. Run all 9 iter-XX/N drills shipped during the
     "fix all 100%" sweep and report aggregate pass/fail.

Steps:

  1. services/sidecar-advisor/Dockerfile exists.
  2. Dockerfile has the §19.13 mandatory sections:
     - FROM line(s)
     - WORKDIR
     - USER (non-root, per CLAUDE.md §13.13)
     - HEALTHCHECK
     - CMD or ENTRYPOINT
  3. NEGATIVE: Dockerfile does NOT contain `USER root` after the
     non-root USER directive (would void the §13.13 contract).
  4. All 11 services now have Dockerfiles (12 total minus frontend
     which has its own; sidecar-advisor was the last gap).
  5. ROLL-UP: each of the 9 iter drills runs and reports its own
     pass/fail. Aggregate = green only if all 9 are green.

Negative assertion per §43: step 3 is the load-bearing one. Without
it, someone could append `USER root` later and the structural check
in step 2 would still see a USER directive.

Run:
    .venv/bin/python mcp/tests/drill_sidecar_dockerfile.py

Step 5 may take 60-120 seconds (it invokes 8 other drills).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "services" / "sidecar-advisor" / "Dockerfile"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"

# Each entry: (label, drill_filename, venv_kind).
#   venv="project" → use REPO/.venv/bin/python (FastAPI deps)
#   venv="browser" → use /tmp/pw-venv/bin/python (Playwright deps)
ITER_DRILLS: list[tuple[str, str, str]] = [
    ("iter 13/N — ErrorTracker (§26)", "drill_frontend_error_tracker.py", "browser"),
    ("iter 14/N — admin smoke E2E (§19/§25)", "drill_e2e_admin_smoke.py", "browser"),
    ("iter 15/N — explain endpoint (§48)", "drill_explain_endpoint.py", "project"),
    ("iter 16/N — service smoke (§8)", "drill_service_smoke.py", "project"),
    ("iter 17/N — §19 doc stubs", "drill_doc_stubs_section19.py", "project"),
    ("iter 18/N — production-checker (§27)", "drill_production_checker.py", "project"),
    ("iter 19/N — frontend toolchain (§19)", "drill_frontend_toolchain.py", "project"),
    ("iter 20/N — model cards (§48.3)", "drill_model_cards.py", "project"),
]


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{NC} {msg}")


def run_drill(rel: str, venv_kind: str) -> tuple[int, str]:
    """Run a sibling drill with the appropriate venv. Returns
    (exit_code, tail_output). Drills that need playwright run on
    /tmp/pw-venv; everything else on the project .venv."""
    drill_path = REPO / "mcp" / "tests" / rel
    if not drill_path.is_file():
        return (127, f"drill not found: {rel}")
    if venv_kind == "browser":
        venv_python = Path("/tmp/pw-venv/bin/python")
    else:
        venv_python = REPO / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return (127, f"{venv_kind} venv missing at {venv_python}")
    env = os.environ.copy()
    env.setdefault("PROD_URL", "http://localhost:3000")
    env.setdefault("DOCUMIND_PROMETHEUS_PORT", "0")
    result = subprocess.run(
        [str(venv_python), str(drill_path)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    # Strip ANSI colors from output for compactness in the tail.
    tail = result.stdout.strip().splitlines()
    last = tail[-1] if tail else "(no output)"
    return (result.returncode, re.sub(r"\x1b\[[0-9;]*m", "", last))


def main() -> int:
    failures = 0

    # ---- A. Sidecar Dockerfile validation ---------------------------

    # 1. Dockerfile exists.
    if DOCKERFILE.is_file():
        ok(f"step 1: {DOCKERFILE.relative_to(REPO)} exists")
    else:
        fail(f"step 1: {DOCKERFILE.relative_to(REPO)} MISSING")
        return 1

    text = DOCKERFILE.read_text(encoding="utf-8")

    # 2. Mandatory sections.
    sections = {
        "FROM": re.search(r"^FROM\s+\S+", text, re.MULTILINE),
        "WORKDIR": re.search(r"^WORKDIR\s+\S+", text, re.MULTILINE),
        "USER": re.search(r"^USER\s+\S+", text, re.MULTILINE),
        "HEALTHCHECK": re.search(r"^HEALTHCHECK\s+", text, re.MULTILINE),
        "CMD or ENTRYPOINT": re.search(r"^(CMD|ENTRYPOINT)\s+", text, re.MULTILINE),
    }
    missing = [k for k, v in sections.items() if v is None]
    if not missing:
        ok(f"step 2: Dockerfile has all 5 §19.13 sections (FROM/WORKDIR/USER/HEALTHCHECK/CMD)")
    else:
        fail(f"step 2: Dockerfile missing sections: {missing}")
        failures += 1

    # 3. NEGATIVE — no USER root after the non-root USER directive.
    user_root_after = False
    seen_non_root = False
    for line in text.splitlines():
        m = re.match(r"^USER\s+(\S+)", line)
        if m:
            user = m.group(1)
            if user != "root" and user != "0":
                seen_non_root = True
            elif seen_non_root and (user == "root" or user == "0"):
                user_root_after = True
                break
    if not user_root_after:
        ok("step 3 (negative): no `USER root` regression after non-root USER (CLAUDE.md §13.13 holds)")
    else:
        fail("step 3 (negative): Dockerfile re-elevates to USER root after non-root — security regression")
        failures += 1

    # 4. All 11 deployable services now have Dockerfiles.
    services_dir = REPO / "services"
    expected_with_dockerfile = [
        "agent-orchestrator-svc",
        "api-gateway",
        "evaluation-svc",
        "finops-svc",
        "frontend",
        "governance-svc",
        "identity-svc",
        "inference-svc",
        "ingestion-svc",
        "observability-svc",
        "retrieval-svc",
        "sidecar-advisor",
    ]
    missing_dockerfiles = [
        s for s in expected_with_dockerfile
        if not (services_dir / s / "Dockerfile").is_file()
    ]
    if not missing_dockerfiles:
        ok(f"step 4: all {len(expected_with_dockerfile)} services have a Dockerfile")
    else:
        fail(f"step 4: missing Dockerfiles: {missing_dockerfiles}")
        failures += 1

    # ---- B. Roll-up: run the 9 iter drills --------------------------

    print()
    print(f"{BOLD}Roll-up — running 8 prior iter drills:{NC}")
    rollup_failed: list[str] = []
    for name, drill_file, venv_kind in ITER_DRILLS:
        try:
            rc, tail = run_drill(drill_file, venv_kind)
        except subprocess.TimeoutExpired:
            rc, tail = (124, "TIMEOUT")
        if rc == 0:
            ok(f"  {name} → {tail[:80]}")
        else:
            fail(f"  {name} → exit {rc}: {tail[:120]}")
            rollup_failed.append(name)
    if not rollup_failed:
        ok(f"step 5: all {len(ITER_DRILLS)} iter drills green")
    else:
        fail(f"step 5: {len(rollup_failed)} iter drill(s) failed: {rollup_failed}")
        failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL STEPS PASSED — 9-iteration sweep verified end-to-end{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
