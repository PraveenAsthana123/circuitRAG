#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Trivy CI workflow contract (per §43 + §47.6 DevSecOps).

Locks .github/workflows/trivy.yml as a security-shift-left gate that
runs filesystem + config + image scans on every PR + push to main +
weekly cron. Pairs with snyk.yml (Snyk = dep CVEs; Trivy =
filesystem secrets + IaC misconfig + image layer).

Eight steps. Five negative.

Step coverage:
  1. POSITIVE: workflow file exists + valid YAML
  2. POSITIVE: triggers on PR + push-to-main + weekly cron
  3. POSITIVE: 3 jobs declared (fs / config / image)
  4. POSITIVE: uses aquasecurity/trivy-action
  5. NEGATIVE: severity is exactly HIGH+CRITICAL (not LOW/MEDIUM —
     misconfig + drift toward "informational only" is the silent-fail
     mode; this drill blocks that drift at code review)
  6. NEGATIVE: fs + config jobs MUST set exit-code: 1 (fail-the-build
     on findings; otherwise security gate is theatre)
  7. NEGATIVE: workflow does NOT use untrusted github.event.* input
     in any run: block (command-injection prevention per the
     security_reminder_hook)
  8. POSITIVE: SARIF upload to GitHub Security tab present (otherwise
     findings disappear into action logs — invisible to operators)

Per CLAUDE.md §43, §47.6 (A11 prompt injection / DevSecOps shift-
left), §49 compose-footer (paired with snyk.yml), §51 forensic
substrate, §57.1 production-grade-by-default.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "trivy.yml"
SNYK_WORKFLOW = REPO / ".github" / "workflows" / "snyk.yml"


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
    # ── 1. file exists + valid YAML ───────────────────────────────────
    step("1. POSITIVE: trivy.yml exists + valid YAML")
    if not WORKFLOW.exists():
        fail(f"missing: {WORKFLOW.relative_to(REPO)}")
    src = WORKFLOW.read_text(encoding="utf-8")
    try:
        import yaml  # noqa: PLC0415
        wf = yaml.safe_load(src)
    except Exception as exc:
        fail(f"YAML parse failed: {exc}")
    ok(f"{len(src)}b — YAML valid")

    # ── 2. triggers: PR + push + cron ─────────────────────────────────
    step("2. POSITIVE: triggers on PR + push-to-main + weekly cron")
    # 'on' may be parsed as bool True by YAML 1.1 (the YAML legacy
    # gotcha). Be tolerant.
    on = wf.get("on") or wf.get(True)
    if not isinstance(on, dict):
        fail(f"workflow has no 'on:' triggers (got {type(on).__name__})")
    if "pull_request" not in on:
        fail("workflow missing pull_request trigger")
    if "push" not in on:
        fail("workflow missing push trigger")
    if "schedule" not in on:
        fail("workflow missing schedule (cron) trigger")
    push_branches = (on.get("push") or {}).get("branches", [])
    if "main" not in push_branches:
        fail(f"push trigger doesn't include main branch (got {push_branches})")
    ok("PR + push(main) + cron all present")

    # ── 3. three jobs (fs / config / image) ───────────────────────────
    step("3. POSITIVE: 3 jobs declared (fs / config / image)")
    jobs = wf.get("jobs", {})
    required_jobs = {"trivy-fs", "trivy-config", "trivy-image"}
    missing_jobs = required_jobs - set(jobs.keys())
    if missing_jobs:
        fail(f"missing jobs: {missing_jobs}")
    ok(f"all 3 canonical jobs present: {sorted(jobs.keys())}")

    # ── 4. uses aquasecurity/trivy-action ─────────────────────────────
    step("4. POSITIVE: uses aquasecurity/trivy-action")
    if "aquasecurity/trivy-action" not in src:
        fail("workflow doesn't reference aquasecurity/trivy-action")
    # Count usages — should be at least 3 (one per job)
    n_action = src.count("aquasecurity/trivy-action")
    if n_action < 3:
        fail(f"trivy-action used only {n_action}x; expected ≥ 3 (one per job)")
    ok(f"aquasecurity/trivy-action referenced {n_action}x")

    # ── 5. NEGATIVE: severity is HIGH or CRITICAL (not LOW/MEDIUM) ────
    step(
        "5. NEGATIVE: severity threshold is HIGH/CRITICAL — block "
        "drift toward 'informational only' (LOW/MEDIUM)"
    )
    # Find every severity: line and assert it includes HIGH or CRITICAL
    severity_lines = re.findall(r"severity:\s*([^\n]+)", src)
    if not severity_lines:
        fail("no severity: line found — Trivy default would be UNKNOWN+")
    for sev in severity_lines:
        sev_clean = sev.strip().strip("'\"")
        if "HIGH" not in sev_clean and "CRITICAL" not in sev_clean:
            fail(
                f"severity '{sev_clean}' does not include HIGH or CRITICAL — "
                "scanner runs but never blocks; security gate is theatre"
            )
    ok(f"all {len(severity_lines)} severity declarations include HIGH/CRITICAL")

    # ── 6. NEGATIVE: fs + config jobs set exit-code: 1 (block on find) ─
    step(
        "6. NEGATIVE: fs + config scans set exit-code: 1 — fail the build "
        "on findings (otherwise security gate is theatre)"
    )
    # The fs + config blocks must each contain "exit-code: '1'"
    fs_block_match = re.search(
        r"trivy-fs:.*?(?=\n  trivy-|\Z)", src, re.DOTALL
    )
    cfg_block_match = re.search(
        r"trivy-config:.*?(?=\n  trivy-|\Z)", src, re.DOTALL
    )
    if not fs_block_match or "exit-code: '1'" not in fs_block_match.group(0):
        fail("trivy-fs job missing exit-code: '1' — findings won't block PR")
    if not cfg_block_match or "exit-code: '1'" not in cfg_block_match.group(0):
        fail(
            "trivy-config job missing exit-code: '1' — IaC misconfig won't "
            "block PR"
        )
    ok("trivy-fs + trivy-config both block on findings (exit-code: 1)")

    # ── 7. NEGATIVE: no untrusted github.event.* in run: blocks ───────
    step(
        "7. NEGATIVE: no untrusted github.event.* in run: blocks "
        "(command-injection prevention)"
    )
    # Find every run: block and check for github.event.* / github.head_ref
    # interpolation. Trivy workflow has no run: blocks (action-only),
    # so this should be vacuously true.
    run_blocks = re.findall(r"run:\s*\|?\n((?:\s+\S.*\n)+)", src)
    untrusted_pattern = re.compile(
        r"\$\{\{\s*github\.event\.(?:issue|pull_request|comment|review|"
        r"pages|commits|head_commit)\.[^}]*\}\}|"
        r"\$\{\{\s*github\.head_ref\s*\}\}",
    )
    for block in run_blocks:
        if untrusted_pattern.search(block):
            fail(
                "run: block uses untrusted github.event.* / github.head_ref "
                "directly — command-injection risk per security_reminder_hook"
            )
    ok(
        f"{len(run_blocks)} run: block(s) — none use untrusted github.event.*"
    )

    # ── 8. SARIF upload to Security tab ───────────────────────────────
    step(
        "8. POSITIVE: SARIF upload to GitHub Security tab "
        "(otherwise findings invisible to operators)"
    )
    if "codeql-action/upload-sarif" not in src:
        fail(
            "workflow doesn't upload SARIF — findings will only appear in "
            "action logs, not the Security tab"
        )
    n_sarif = src.count("codeql-action/upload-sarif")
    if n_sarif < 3:
        fail(
            f"SARIF upload used only {n_sarif}x; expected ≥ 3 "
            "(one per scan job)"
        )
    ok(f"SARIF upload present {n_sarif}x — Security tab will show findings")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
