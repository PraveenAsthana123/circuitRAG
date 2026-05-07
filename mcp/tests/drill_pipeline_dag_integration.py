#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for D2 — control-plane page mounts PipelineDagPanel (Phase D2).

Source-level verification:
  - control-plane/page.tsx imports PipelineDagPanel + named exports
  - <PipelineDagPanel /> is rendered with stages derived from task_runs
  - derivation function exists and reads routing_decision defensively

Negative assertions:
  1. Import path is RELATIVE to the page (./PipelineDagPanel) — wrong
     path = silent dead component
  2. Component is rendered inside the selectedTask block (not at page
     root) so it shows per-task data
  3. routing_decision read MUST be defensive (TS type doesn't include
     it yet) — drill verifies the cast is present
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "agentic" / "control-plane" / "page.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx imports PipelineDagPanel --")
    text = PAGE.read_text(encoding="utf-8")
    assert "PipelineDagPanel" in text, "page.tsx must import PipelineDagPanel"
    print("  ok: PipelineDagPanel referenced")

    print("-- 2. NEGATIVE: import path is relative './PipelineDagPanel' --")
    # A wrong path (e.g. '../../components/PipelineDagPanel') would
    # resolve at compile but render nothing useful at runtime if the
    # file lives elsewhere — the panel ships next to page.tsx.
    assert "from './PipelineDagPanel'" in text, (
        "import must be './PipelineDagPanel' (relative to page); "
        "wrong path = silent dead component"
    )
    print("  ok: import is './PipelineDagPanel' (panel ships next to page)")

    print("-- 3. POSITIVE: derivation function exists --")
    assert "function derivePipelineStages(" in text or "derivePipelineStages =" in text, (
        "page.tsx must define derivePipelineStages() to map task_runs → stages"
    )
    print("  ok: derivePipelineStages defined")

    print("-- 4. POSITIVE: derivation maps run.phase → role_id --")
    # The derivation walks PIPELINE_STAGES and looks up by role_id; verify
    # the lookup pattern is present.
    assert "latestByPhase" in text or "byPhase" in text, (
        "derivation should aggregate runs by phase/role_id"
    )
    print("  ok: phase-keyed run aggregation present")

    print("-- 5. POSITIVE: <PipelineDagPanel /> rendered with stages prop --")
    assert "<PipelineDagPanel" in text, "panel component must be rendered, not just imported"
    assert "stages={derivePipelineStages(taskRuns)" in text, (
        "stages prop must be wired from derivation"
    )
    assert "totalCostCents=" in text, "totalCostCents prop must be wired"
    print("  ok: panel rendered with stages + totalCostCents wired")

    print("-- 6. NEGATIVE: panel rendered INSIDE selectedTask block --")
    # The panel should appear AFTER 'selectedTask' is checked, not at
    # page root — otherwise it's static for all tasks and useless.
    panel_idx = text.find("<PipelineDagPanel")
    selected_idx = text.find("selectedTask ? (")
    assert panel_idx > selected_idx >= 0, (
        "PipelineDagPanel must render INSIDE selectedTask conditional"
    )
    print("  ok: panel rendered inside selectedTask conditional")

    print("-- 7. NEGATIVE: routing_decision read is defensive --")
    # AgenticTaskRun TS type doesn't yet include routing_decision; the
    # derivation must cast via Record<string, unknown> to read it
    # without a TS error.
    assert "routing_decision" in text, "derivation must read routing_decision"
    assert "Record<string, unknown>" in text, (
        "routing_decision read must use defensive cast (TS type doesn't include it)"
    )
    print("  ok: defensive cast for routing_decision")

    print("-- 8. POSITIVE: cost summed across runs (matches §48 audit) --")
    assert ".reduce(" in text and "cost_usd_cents" in text, (
        "totalCostCents must sum cost_usd_cents across runs"
    )
    print("  ok: total cost summed via .reduce")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
