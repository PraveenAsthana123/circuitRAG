# RESOURCES: readonly
"""
Drill: pip-audit is wired into CI as a blocking step.

Per CLAUDE.md §16 (deps mgmt: vulnerability scanning in CI on every
PR), §43 (drill discipline; ≥3 negatives), §45.4 (no checkbox flips
without code), §52 row 4 (operator API gap).

The architecture matrix listed Security/pip-audit as ⚠️ partial
("not in CI yet"). Empirical truth: pip-audit WAS in CI but as
`|| true` (non-blocking) — a CVE landing wouldn't fail the build.
Iter-33 flips it to blocking AND locks the contract here so future
changes can't silently re-soft-fail it.

Locks (positive):
  L1. .github/workflows/ci.yml has a step named pip-audit
  L2. The step covers all 4 service requirements files (full
      transitive surface; missing one creates a blind spot)
  L3. The step uses --strict (any CVE = exit 1)

Locks (negative — ≥3 per §43):
  N1. The step does NOT contain `|| true` — that would silently
      mask CVE failures (the prior-iter regression we're fixing)
  N2. The step does NOT contain `--ignore-vuln` without an explicit
      catalog comment — accidental allowlist additions are a soft
      regression. (We allow ignores ONLY if a catalog comment
      "# IGNORE: <CVE-ID> <reason> <expiry>" is on a nearby line.)
  N3. The pip-audit step is in the `python` job's steps (not in a
      detached job that doesn't gate the merge)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

REQUIRED_REQS = (
    "services/ingestion-svc/requirements.txt",
    "services/retrieval-svc/requirements.txt",
    "services/inference-svc/requirements.txt",
    "services/evaluation-svc/requirements.txt",
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    if not CI_WORKFLOW.exists():
        fail(f"CI workflow missing: {CI_WORKFLOW.relative_to(REPO)}")

    src = CI_WORKFLOW.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: pip-audit step exists
    # ------------------------------------------------------------------
    step("1. pip-audit step exists in ci.yml")
    if "pip-audit" not in src:
        fail("ci.yml has no pip-audit reference at all")
    # The step name should call out pip-audit
    if not re.search(r"name:\s*pip-audit", src):
        fail("no `name: pip-audit` step header found")
    ok("pip-audit step header present")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: all 4 service requirements files covered
    # ------------------------------------------------------------------
    step("2. all 4 service requirements files covered by the scan")
    missing = [r for r in REQUIRED_REQS if r not in src]
    if missing:
        fail(f"requirements files NOT covered by pip-audit: {missing}")
    ok(f"all {len(REQUIRED_REQS)} service requirements files covered")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: --strict flag is used
    # ------------------------------------------------------------------
    step("3. --strict flag present (any CVE → exit 1)")
    # Locate the pip-audit run line and confirm --strict is there
    pip_audit_run = re.search(
        r"run:\s*pip-audit\s+([^\n]*)",
        src,
    )
    if pip_audit_run is None:
        fail("could not locate the pip-audit run line")
    flags = pip_audit_run.group(1)
    if "--strict" not in flags:
        fail(f"pip-audit run missing --strict; got: {flags[:100]}")
    ok("--strict flag present")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: NO `|| true` (would silently mask CVEs)
    # ------------------------------------------------------------------
    step("4. NEGATIVE: no `|| true` masking the pip-audit exit code")
    # Scope the check to the pip-audit step. Look at the step's run line +
    # the next few lines for any `|| true`.
    pip_audit_block = re.search(
        r"name:\s*pip-audit[^\n]*\n(?:[^\n]*\n){0,8}",
        src,
    )
    if pip_audit_block is None:
        fail("could not locate pip-audit block for `|| true` check")
    block = pip_audit_block.group(0)
    if "|| true" in block:
        fail(
            "pip-audit step contains `|| true` — CVE failures would be "
            "silently masked. Remove the suffix to make pip-audit blocking."
        )
    ok("no `|| true` in pip-audit step (CVE failures will block CI)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: --ignore-vuln only with catalog comment
    # ------------------------------------------------------------------
    step("5. NEGATIVE: --ignore-vuln entries require catalog comment")
    if "--ignore-vuln" in block:
        # If used, the step must have an inline comment block giving
        # CVE id + reason + expiry on a nearby line. Looking for the
        # pattern "# IGNORE: <CVE> <reason>" within the same block.
        if not re.search(r"#\s*IGNORE:\s*\S+", block):
            fail(
                "--ignore-vuln present but no catalog comment "
                "(# IGNORE: <CVE-ID> <reason> <expiry>) nearby. "
                "Accidental allowlists are soft regressions."
            )
        ok("--ignore-vuln present WITH catalog comment (intentional)")
    else:
        ok("no --ignore-vuln entries; catalog clean")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: pip-audit is in a job that gates merge
    # ------------------------------------------------------------------
    step("6. NEGATIVE: pip-audit step is in the `python` job (gates merge)")
    # Find the `python:` job header, then ensure pip-audit appears
    # between it and the next top-level job header.
    py_job_match = re.search(
        r"^\s{2}python:\s*\n(?:.*\n)*?(?=^\s{2}\w+:|\Z)",
        src, re.MULTILINE,
    )
    if py_job_match is None:
        fail("could not locate `python:` job in ci.yml")
    py_job_body = py_job_match.group(0)
    if "pip-audit" not in py_job_body:
        fail(
            "pip-audit is NOT inside the `python:` job — if it's in a "
            "detached/non-required job, it doesn't gate merge"
        )
    ok("pip-audit lives inside the `python:` job (merge-gating)")

    print(f"\n{GREEN}{BOLD}ALL 6 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
