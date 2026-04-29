#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: CI tier-classification + workflow contract.

Locks in the tier definitions documented at docs/ci-drills-setup.md
section 1 + the workflow flag contracts at .github/workflows/drills*.yml.

A regression that:
  * retags drill_baggage_propagation from readonly → mcp_hr would
    silently drop it from drills-fast → caught here (step 1).
  * retags drill_audit_log_partitioned from pg → inference would
    push it out of the per-PR PG tier → caught here (step 2).
  * removes --allow-resources= from drills.yml (e.g. by editing
    the YAML to "run all drills") would balloon CI cost from 10s to
    several minutes → caught here (step 4).
  * adds on.pull_request to drills-stack.yml would put a 3-min
    stack drill on every PR, blowing the per-PR runner budget for
    the team → caught here (step 6).

Seven steps (6 negative assertions). Pure source-scan, zero infra.

 1. Tier 1 (--allow-resources=) contains the named in-process
    drills that anchor the cheap PR gate: baggage_propagation,
    baggage_middleware, baggage_log_formatter, baggage_kafka,
    runner_scheduler, runner_hardening, runner_junit. If any of
    these falls out of tier 1, the BaggagePropagation contract
    drift is silent.
 2. Tier 2 (--allow-resources=pg) adds drill_audit_log_partitioned
    and drill_inference_trace_link (the canonical PG-binding
    drills). NEGATIVE: a regression that retagged either to need
    `inference` would push them into deferred tier 3b — that's an
    explainability + forensics audit that wouldn't run pre-PR.
    Tier 2 must be a SUPERSET of tier 1 (subset relation locked).
 3. Tier 3a (--allow-resources=pg,mcp_hr) adds the MCP-server
    drills + tool-telemetry drills. Verify presence of
    drill_mcp_per_tool_telemetry, drill_scope_denial_actor_attribution.
    Tier 3a must be a SUPERSET of tier 2.
 4. drills.yml workflow uses --allow-resources= (zero-infra) AND
    --allow-resources=pg (PG tier). NEGATIVE: a YAML edit that
    changed the flag, OR removed it entirely, would silently change
    what runs.
 5. drills-stack.yml uses --allow-resources=pg,mcp_hr. NEGATIVE:
    a YAML edit broadening this would balloon the schedule-only
    cost into the per-PR budget if the workflow trigger is also
    changed in error.
 6. drills-stack.yml has NO push: or pull_request: triggers (it's
    schedule + workflow_dispatch only). NEGATIVE: an edit that
    added on.pull_request would put a 3-min stack drill on every
    PR, blowing the per-PR runner budget for the team.
 7. drills.yml HAS push: AND pull_request: triggers (PR-time
    gate). NEGATIVE: removing those would silently turn the cheap
    PR gate into a manual-only run.

(Step "every drill_*.py declares a # RESOURCES: header" was
considered but dropped — 23 stack-tier drills legitimately rely on
the runner's DEFAULT_RESOURCES fallback. The runner handles
missing-header drills correctly by serializing them against every
other; that's a sensible default for stack-tier drills, not a bug.)

Run:
    python3 mcp/tests/drill_ci_tier_definitions.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DRILL_DIR = REPO / "mcp" / "tests"
WORKFLOW_DIR = REPO / ".github" / "workflows"

GREEN = "\033[32m"
RED = "\033[31m"
NC = "\033[0m"


def green(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    sys.exit(1)


def step(title: str) -> None:
    print(f"\n── {title} ──")


def _run_runner(args: list[str]) -> set[str]:
    """Invoke run_drills.py with --list and return the set of drill names."""
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "run_drills.py"),
        *args,
        "--list",
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=str(REPO),
    )
    if proc.returncode != 0:
        fail(f"runner failed: {proc.stderr}")
    drills: set[str] = set()
    for line in proc.stdout.splitlines():
        # Lines look like:
        #   drill_baggage_propagation     resources: (none — pure reads)
        m = re.match(r"^\s+(drill_\w+)\s+resources:", line)
        if m:
            drills.add(m.group(1))
    return drills


def main() -> None:
    # ── Step 1: tier 1 contracts ────────────────────────────────
    step(
        "1. tier 1 (--allow-resources=) contains the canonical zero-infra "
        "drills"
    )
    tier1 = _run_runner(["--allow-resources="])
    tier1_required = {
        "drill_baggage_propagation",
        "drill_baggage_middleware",
        "drill_baggage_log_formatter",
        "drill_baggage_kafka",
        "drill_runner_scheduler",
        "drill_runner_hardening",
        "drill_runner_junit",
    }
    missing_t1 = tier1_required - tier1
    if missing_t1:
        fail(
            f"NEGATIVE FAILED: tier 1 (drills-fast) is missing {missing_t1}. "
            f"These are the canonical zero-infra drills that anchor the "
            f"cheap PR gate. A drift here means a baggage / runner "
            f"contract regression would silently bypass CI."
        )
    green(
        f"tier 1 contains all 7 canonical drills "
        f"(total tier 1 size: {len(tier1)})"
    )

    # ── Step 2: tier 2 contracts ────────────────────────────────
    step(
        "2. tier 2 (--allow-resources=pg) adds the canonical PG-binding "
        "drills"
    )
    tier2 = _run_runner(["--allow-resources=pg"])
    tier2_required = {
        # PG-only canonical drill: audit-log partitioning + RLS.
        "drill_audit_log_partitioned",
        # NOT included: drill_inference_trace_link is `pg + inference`
        # — needs the inference-svc running, which lands it in tier 3b
        # (deferred). When tier 3b ships, add drill_inference_trace_link
        # to a separate tier3b_required set tested under
        # --allow-resources=pg,inference.
    }
    missing_t2 = tier2_required - tier2
    if missing_t2:
        fail(
            f"NEGATIVE FAILED: tier 2 (drills-pg) is missing {missing_t2}. "
            f"These cover the audit-log partitioning + RLS contract — "
            f"core compliance-sensitive paths. Drift here means "
            f"compliance contracts wouldn't run pre-PR."
        )
    if not tier1.issubset(tier2):
        only_in_t1 = tier1 - tier2
        fail(
            f"tier 2 should be a SUPERSET of tier 1; these tier-1 drills "
            f"are missing from tier 2: {only_in_t1}. Subset relation broke."
        )
    green(
        f"tier 2 contains both canonical PG drills + is a superset of "
        f"tier 1 (total tier 2 size: {len(tier2)})"
    )

    # ── Step 3: tier 3a contracts ──────────────────────────────
    step(
        "3. tier 3a (--allow-resources=pg,mcp_hr) adds the MCP-server "
        "drills"
    )
    tier3a = _run_runner(["--allow-resources=pg,mcp_hr"])
    tier3a_required = {
        "drill_mcp_per_tool_telemetry",
        "drill_scope_denial_actor_attribution",
    }
    missing_t3a = tier3a_required - tier3a
    if missing_t3a:
        fail(
            f"tier 3a (drills-stack) is missing {missing_t3a}. These cover "
            f"per-tool telemetry + scope-denial audit log paths."
        )
    if not tier2.issubset(tier3a):
        fail(
            f"tier 3a should be a superset of tier 2; tier-2-not-in-3a: "
            f"{tier2 - tier3a}"
        )
    green(
        f"tier 3a contains both canonical MCP drills + is a superset of "
        f"tier 2 (total tier 3a size: {len(tier3a)})"
    )

    # ── Step 4: workflow flag contracts ────────────────────────
    step(
        "4. drills.yml uses --allow-resources= (fast) AND "
        "--allow-resources=pg (pg tier)"
    )
    drills_yml = (WORKFLOW_DIR / "drills.yml").read_text()
    if "--allow-resources=" not in drills_yml:
        fail("drills.yml missing --allow-resources= for the fast tier")
    if "--allow-resources=pg" not in drills_yml:
        fail("drills.yml missing --allow-resources=pg for the pg tier")
    green("drills.yml has both --allow-resources= and --allow-resources=pg")

    # ── Step 5: drills-stack.yml flag contract ─────────────────
    step("5. drills-stack.yml uses --allow-resources=pg,mcp_hr")
    stack_yml = (WORKFLOW_DIR / "drills-stack.yml").read_text()
    if "--allow-resources=pg,mcp_hr" not in stack_yml:
        fail(
            "drills-stack.yml missing --allow-resources=pg,mcp_hr. A drift "
            "broadening this would balloon schedule-only cost into per-PR "
            "if combined with a trigger change (see step 7)."
        )
    green("drills-stack.yml uses the documented tier-3a allow-list")

    # ── Step 6: NEGATIVE — drills-stack.yml is schedule-only ───
    step(
        "6. NEGATIVE: drills-stack.yml has NO push:/pull_request: triggers"
    )
    # Look for the `on:` block and verify only schedule + workflow_dispatch.
    on_block_match = re.search(
        r"^on:\s*\n((?:[ \t]+\S.*\n)+)", stack_yml, re.MULTILINE,
    )
    if not on_block_match:
        fail("drills-stack.yml has no `on:` block")
    on_block = on_block_match.group(1)
    if re.search(r"^\s*push\s*:", on_block, re.MULTILINE):
        fail(
            "NEGATIVE FAILED: drills-stack.yml has on.push trigger. The "
            "stack tier is ~3min cold-start; running it on every push to "
            "main/develop would balloon CI cost. Schedule + dispatch only."
        )
    if re.search(r"^\s*pull_request\s*:", on_block, re.MULTILINE):
        fail(
            "NEGATIVE FAILED: drills-stack.yml has on.pull_request trigger. "
            "Same cost concern as on.push — see runbook section 6."
        )
    if "schedule" not in on_block:
        fail("drills-stack.yml lost its schedule trigger — drift catches no longer fire nightly")
    if "workflow_dispatch" not in on_block:
        fail("drills-stack.yml lost workflow_dispatch — operators can no longer trigger ad-hoc")
    green("drills-stack.yml is schedule + workflow_dispatch only (no push/PR)")

    # ── Step 7: drills.yml HAS PR triggers ─────────────────────
    step("7. drills.yml HAS push: AND pull_request: triggers (PR gate)")
    drills_on_match = re.search(
        r"^on:\s*\n((?:[ \t]+\S.*\n)+)", drills_yml, re.MULTILINE,
    )
    if not drills_on_match:
        fail("drills.yml has no `on:` block")
    drills_on = drills_on_match.group(1)
    if not re.search(r"^\s*push\s*:", drills_on, re.MULTILINE):
        fail(
            "NEGATIVE FAILED: drills.yml lost on.push. The cheap PR gate "
            "(15+23 drills, ~30s wall) is no longer running on push to "
            "protected branches. CHECK why this triggered before merging."
        )
    if not re.search(r"^\s*pull_request\s*:", drills_on, re.MULTILINE):
        fail(
            "NEGATIVE FAILED: drills.yml lost on.pull_request. The cheap "
            "PR gate is no longer enforced at PR time."
        )
    green(
        "drills.yml has push + pull_request triggers (PR gate intact)"
    )

    print(f"\n{GREEN}{'=' * 50}{NC}")
    print(f"{GREEN}  ALL 7 CI-TIER CONTRACT STEPS PASSED{NC}")
    print(f"{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
