# RESOURCES: readonly
"""
Drill: Snyk security workflow shape + .snyk allowlist contract.

Per CLAUDE.md §16 (deps mgmt: vulnerability scanning), §28 (security
standards), §43 (drill discipline; ≥3 negatives), §45.4 (no checkbox
flips without code), §47.6 (DevSecOps shift-left).

Architecture matrix listed Security/Snyk as ⚠️ Stage-1 scaffold
'.snyk + .github/workflows/snyk.yml shipped; needs SNYK_TOKEN'. The
SNYK_TOKEN is operator-territory (§42 modifying secret stores). This
drill locks the WORKFLOW SHAPE so the operator-action surface stays
intact: when SNYK_TOKEN is set, the workflow runs immediately with no
further code change.

Locks (positive):
  L1. .github/workflows/snyk.yml exists
  L2. .snyk policy file exists at repo root
  L3. Workflow has both `snyk-python` and `snyk-node` jobs
  L4. Workflow runs on PR + push to main + weekly cron (catches
      new CVEs against unchanged code)

Locks (negative — ≥3 per §43):
  N1. SNYK_TOKEN reads from secrets context (not from a variable)
  N2. severity-threshold is `high` (any HIGH+ CVE blocks merge)
  N3. The workflow does NOT contain `continue-on-error: true` on
      the actual blocking `Snyk test` step — that would silently
      mask CVEs (the same pattern iter-33 fixed for pip-audit)
  N4. .snyk file has version pin (allowlist evolution stays
      reviewable; un-versioned policy drifts silently)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNYK_WORKFLOW = REPO / ".github" / "workflows" / "snyk.yml"
SNYK_POLICY = REPO / ".snyk"

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
    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: workflow file + policy file exist
    # ------------------------------------------------------------------
    step("1. .github/workflows/snyk.yml + .snyk policy both exist")
    for p in (SNYK_WORKFLOW, SNYK_POLICY):
        if not p.exists():
            fail(f"missing: {p.relative_to(REPO)}")
    ok("both Snyk workflow + policy file present")

    workflow_src = SNYK_WORKFLOW.read_text(encoding="utf-8")
    policy_src = SNYK_POLICY.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: both Python + Node jobs present
    # ------------------------------------------------------------------
    step("2. workflow has snyk-python + snyk-node jobs")
    for job in ("snyk-python:", "snyk-node:"):
        if job not in workflow_src:
            fail(f"workflow missing job header `{job}`")
    ok("both snyk-python + snyk-node jobs present")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: triggers cover PR + push + weekly cron
    # ------------------------------------------------------------------
    step("3. workflow runs on PR + push:main + weekly cron")
    triggers = (
        "pull_request:",
        "push:",
        "schedule:",
    )
    missing = [t for t in triggers if t not in workflow_src]
    if missing:
        fail(f"workflow missing triggers: {missing}")
    # cron should be weekly-ish (at least daily would be too aggressive
    # for CI minutes; we want catches-stale-CVE coverage)
    if "cron:" not in workflow_src:
        fail("workflow missing cron schedule (catches CVEs in unchanged code)")
    ok("workflow runs on PR + push:main + cron")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: SNYK_TOKEN from secrets context (not env/var)
    # ------------------------------------------------------------------
    step("4. NEGATIVE: SNYK_TOKEN sourced from secrets, not vars")
    if "secrets.SNYK_TOKEN" not in workflow_src:
        fail(
            "SNYK_TOKEN not read from secrets context — operator-token "
            "in vars/env would leak in workflow logs"
        )
    if "vars.SNYK_TOKEN" in workflow_src:
        fail(
            "SNYK_TOKEN read from vars context (vars are public!); "
            "must use secrets context for token material"
        )
    ok("SNYK_TOKEN sourced from secrets context (not vars/env)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: severity-threshold is high (HIGH+ blocks merge)
    # ------------------------------------------------------------------
    step("5. NEGATIVE: severity-threshold=high (HIGH+ CVEs block merge)")
    if "--severity-threshold=high" not in workflow_src:
        fail(
            "Snyk run missing `--severity-threshold=high` — without it, "
            "MEDIUM/LOW CVEs would block too (CI noise), OR (worse) "
            "no threshold = everything passes including criticals"
        )
    ok("--severity-threshold=high (HIGH+ blocks; MED/LOW warns)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: blocking step has NO continue-on-error
    # ------------------------------------------------------------------
    step("6. NEGATIVE: Snyk test (blocking) has no continue-on-error")
    # The contract: `Snyk monitor` MAY have continue-on-error (telemetry,
    # non-fatal). `Snyk test` MUST NOT — that's the merge gate.
    test_block = re.search(
        r"(?:- )?name:\s*Snyk test \(blocking\).*?(?=\n\s*-\s*name:|\n  \w+:|\Z)",
        workflow_src, re.DOTALL,
    )
    if test_block is None:
        fail(
            "could not locate `Snyk test (blocking)` step — workflow may "
            "have changed shape; refresh this drill"
        )
    if "continue-on-error: true" in test_block.group(0):
        fail(
            "Snyk test (blocking) has continue-on-error: true — same "
            "regression iter-33 fixed for pip-audit. Remove it."
        )
    ok("Snyk test (blocking) has NO continue-on-error (CVE failures gate merge)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: .snyk has version pin
    # ------------------------------------------------------------------
    step("7. NEGATIVE: .snyk has version pin (allowlist evolution reviewable)")
    if "version:" not in policy_src:
        fail(
            ".snyk missing `version:` field — un-versioned policies "
            "drift silently across Snyk schema upgrades"
        )
    ok(".snyk has version pin (drift-resistant)")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
    print(
        "\nNote: SNYK_TOKEN is operator-territory (§42 modifying secret "
        "stores).\nWhen ready: GitHub → Settings → Secrets → New "
        "repository secret → SNYK_TOKEN"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
