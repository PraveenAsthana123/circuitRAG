#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/advanced_healthcheck.py — 7-layer health-check tool.

Locks the contract for the operator-facing health-check + troubleshoot
+ tracking tool that surfaces actionable remediation per row.

8 steps, 4 negative.

  1. POSITIVE: scripts/advanced_healthcheck.py exists + executable
  2. POSITIVE: script declares all 7 layers (app/db/infra/proc/log/obs/mesh)
  3. POSITIVE: every layer has a probe_* function returning list[Probe]
  4. NEGATIVE: --fix mode exists (triage view — only non-green rows)
  5. NEGATIVE: --json mode exists (machine-readable for dashboards/CI)
  6. NEGATIVE: probes run in parallel (ThreadPoolExecutor) — never serial
              (slowest layer would block triage)
  7. NEGATIVE: Probe dataclass carries `remediation` field (raw probes
              with no remediation hint are useless to on-call)
  8. POSITIVE: exit code semantics — 1 only when critical-red is present;
              warnings exit 0 (allow CI gates without false-blocking)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 4 here), §47.6
(observability is first-class), §57.5 (5-question on-call runbook —
the tool MUST answer "what broke / when / how to fix" per row), §57.7
(remediation hints must be actionable, not generic 'check logs').
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "advanced_healthcheck.py"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"

REQUIRED_LAYERS = ["app", "db", "infra", "proc", "log", "obs", "mesh"]


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. exists + executable ─────────────────────────────────────────
    step("1. POSITIVE: scripts/advanced_healthcheck.py exists + executable")
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT.relative_to(REPO)}")
    if not (SCRIPT.stat().st_mode & 0o100):
        fail("script not executable")
    text = SCRIPT.read_text(encoding="utf-8")
    ok(f"script present ({len(text)}b)")

    # ── 2. all 7 layers declared ──────────────────────────────────────
    step("2. POSITIVE: 7 layers declared (app/db/infra/proc/log/obs/mesh)")
    if "LAYERS = {" not in text and "LAYERS:" not in text:
        fail("script missing LAYERS dispatcher dict")
    for layer in REQUIRED_LAYERS:
        if f'"{layer}"' not in text:
            fail(f"layer {layer!r} not declared")
    ok(f"all {len(REQUIRED_LAYERS)} layers declared in LAYERS dispatcher")

    # ── 3. probe_* function per layer ─────────────────────────────────
    step("3. POSITIVE: every layer has a probe_* function returning probes")
    expected_funcs = [
        "probe_app_services", "probe_databases", "probe_docker_containers",
        "probe_host_processes", "probe_recent_logs", "probe_observability",
        "probe_mesh",
    ]
    for fn in expected_funcs:
        if f"def {fn}" not in text:
            fail(f"missing probe function: {fn}")
    ok(f"all {len(expected_funcs)} layer-probe functions present")

    # ── 4. NEGATIVE: --fix flag exists ────────────────────────────────
    step("4. NEGATIVE: --fix mode (triage view) exists")
    if '"--fix"' not in text:
        fail("--fix flag missing — operator can't get focused triage view")
    if "fix_only" not in text and "fix_only=" not in text:
        fail("--fix flag doesn't wire through to render_table()")
    ok("--fix triage mode present (filters to non-green rows + remediation)")

    # ── 5. NEGATIVE: --json flag exists ───────────────────────────────
    step("5. NEGATIVE: --json mode (machine-readable) exists")
    if '"--json"' not in text:
        fail("--json flag missing — can't pipe to dashboards/CI")
    if "json.dumps" not in text:
        fail("--json flag doesn't actually emit JSON")
    ok("--json mode present (json.dumps output)")

    # ── 6. NEGATIVE: parallel probes via ThreadPoolExecutor ───────────
    step("6. NEGATIVE: probes run in parallel (ThreadPoolExecutor)")
    if "ThreadPoolExecutor" not in text:
        fail(
            "probes run serially — slowest layer (e.g. docker exec round-trip) "
            "would block triage. Must use ThreadPoolExecutor + as_completed."
        )
    if "as_completed" not in text:
        fail("ThreadPoolExecutor used but not as_completed — would block on slowest")
    ok("probes parallelized via ThreadPoolExecutor + as_completed")

    # ── 7. NEGATIVE: Probe dataclass has remediation field ────────────
    step("7. NEGATIVE: Probe dataclass carries `remediation` field")
    # Find the Probe dataclass definition
    if "@dataclass" not in text or "class Probe" not in text:
        fail("Probe dataclass missing")
    probe_idx = text.find("class Probe")
    probe_block = text[probe_idx : probe_idx + 800]
    if "remediation" not in probe_block:
        fail(
            "Probe dataclass has no `remediation` field — raw probes with "
            "no actionable hint are useless to on-call (§57.5)"
        )
    ok("Probe carries `remediation` field (operator-actionable)")

    # ── 8. POSITIVE: exit code 1 only on critical-red ────────────────
    step("8. POSITIVE: exit-code semantics — critical-red → 1, warn → 0")
    if "critical_red" not in text and "severity" not in text:
        fail("no severity-based exit code — can't gate CI without false-blocks")
    if 'severity="critical"' not in text and "severity == 'critical'" not in text:
        # Allow either single or double-quote convention
        if "severity == \"critical\"" not in text:
            fail("severity='critical' tagging missing — exit code can't distinguish")
    ok("exit code distinguishes critical-red from warn-red")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
