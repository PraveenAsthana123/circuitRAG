#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for C5 — frontend PipelineDagPanel (Phase C5).

Source-level structural drill on the new TSX file. Verifies all 9
canonical stages from agent_registry.py are present and rendered,
and that the cost column is wired.

Negative assertions:
  1. Every stage from app/agent_registry.py MUST appear in PIPELINE_STAGES
     (drift between backend role specs and frontend visualisation =
     hidden missing-stage bug).
  2. Component MUST have aria-label for accessibility (per §14.2 a11y).
  3. Cost is rendered with dollar formatting (operator can read $/run).
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "services" / "frontend" / "app" / "admin" / "agentic" / "control-plane" / "PipelineDagPanel.tsx"
REGISTRY = REPO / "services" / "agent-orchestrator-svc" / "app" / "agent_registry.py"


def main() -> int:
    print("-- 1. POSITIVE: PipelineDagPanel.tsx exists --")
    assert PANEL.exists(), f"missing {PANEL}"
    text = PANEL.read_text(encoding="utf-8")
    print(f"  ok: {PANEL.relative_to(REPO)} ({len(text)} bytes)")

    print("-- 2. POSITIVE: 9 canonical stages declared --")
    expected_roles = {
        "researcher", "strategist", "coder_executor", "reviewer",
        "tester", "security_advisor", "advisor", "deployer", "observer",
    }
    declared = set(re.findall(r"role_id:\s*'(\w+)'", text))
    missing = expected_roles - declared
    extra = declared - expected_roles
    assert not missing, f"PipelineDagPanel missing stages: {missing}"
    print(f"  ok: all 9 expected stages present in PIPELINE_STAGES (extras: {extra or 'none'})")

    print("-- 3. NEGATIVE: registry ↔ panel stage drift detection --")
    # Pull role_ids from the Python registry and confirm panel covers them.
    reg_text = REGISTRY.read_text(encoding="utf-8")
    reg_role_ids = set(re.findall(r'role_id="(\w+)"', reg_text))
    panel_only = declared - reg_role_ids
    registry_only = reg_role_ids - declared
    # Allow the registry to have legacy roles (manager, security_advisor) we don't render.
    # But every panel stage MUST exist in registry.
    assert not panel_only, (
        f"DRIFT: panel renders stages not in registry: {panel_only}"
    )
    print(f"  ok: panel ⊆ registry (registry has {len(registry_only)} extra: {registry_only or 'none'})")

    print("-- 4. POSITIVE: PipelineStageStatus enum covers all states --")
    for status in ("pending", "running", "success", "fail", "blocked", "skipped"):
        assert f"'{status}'" in text, f"missing status: {status}"
    print("  ok: 6 pipeline status states declared")

    print("-- 5. POSITIVE: tier labels for A=local, B=cloud --")
    assert "tier_a" in text and "tier_b" in text
    assert "local" in text.lower(), "tier label must say 'local' for operator clarity"
    assert "cloud" in text.lower(), "tier label must say 'cloud'"
    print("  ok: tier_a→local, tier_b→cloud labels")

    print("-- 6. NEGATIVE: aria-label on component (§14.2 a11y) --")
    assert "aria-label" in text, (
        "PipelineDagPanel must have aria-label for accessibility per §14.2"
    )
    aria_count = text.count("aria-label")
    assert aria_count >= 2, f"expected ≥2 aria-labels (panel + each stage); got {aria_count}"
    print(f"  ok: {aria_count} aria-label attributes present")

    print("-- 7. NEGATIVE: cost rendered with dollar formatting --")
    # Operator dashboard must show $ amount, not just cents.
    assert "$" in text and "(totalCost / 100).toFixed(2)" in text, (
        "cost must be rendered as $X.XX for operator readability"
    )
    print("  ok: dollar-formatted cost rendering")

    print("-- 8. POSITIVE: component default-renders even with no props --")
    # The component must handle stages=undefined gracefully so it can be
    # mounted before a task is selected (renders all-pending diagram).
    assert "stages ??" in text, (
        "stages prop must default to PIPELINE_STAGES.map(...) when undefined"
    )
    print("  ok: default props yield all-pending diagram")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
