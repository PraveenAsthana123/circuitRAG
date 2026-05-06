"""GEPA chain status reporter — one operator command for the whole pipeline.

Aggregates the seven GEPA stages into a single text report:
  Stage 1-3: dspy + GEPA compile state
  Stage 4:   promotion gate state (gepa_optimized_prompts.json)
  Stage 5:   overlay state (gepa_active_prompts.json)
  Stage 6:   target prompt alignment (Path-B)
  Stage 7:   canary routing state (env flags)

CONTRACT:
  Pure read-only. No env-flag opt-in needed; reads file presence + env
  state to report what's currently configured.

§47 fail-safe: every layer's status read is wrapped in try/except;
missing/malformed files report as "not present" rather than raising.

COMPOSES WITH:
    scripts/run_gepa_empirical.py — Stage-3 compile path
    scripts/promote_gepa_prompts.py — Stage-4 gate
    services/inference-svc/.../prompt_repo.py — Stage-5 overlay + Stage-7 helper
    docs/architecture/gepa-chain-status-and-stage6-blocker.md
    Makefile target: empirical-gepa-status
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Per-stage artifact locations
GEPA_REPORT = REPO / ".loop" / "gepa_optimized_prompts.json"
GEPA_ACTIVE = REPO / ".loop" / "gepa_active_prompts.json"
GEPA_HISTORY = REPO / ".loop" / "gepa_promotion_history.jsonl"


def _load_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_jsonl_count(p: Path) -> tuple[int, int, int]:
    """Returns (total, promoted, rejected) decision counts."""
    if not p.exists():
        return 0, 0, 0
    total = promoted = rejected = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            total += 1
            if row.get("promoted"):
                promoted += 1
            else:
                rejected += 1
    except Exception:
        return 0, 0, 0
    return total, promoted, rejected


def _format_age(ts: float) -> str:
    if not ts:
        return "(unknown)"
    delta = time.time() - ts
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta/60)}m ago"
    if delta < 86400:
        return f"{int(delta/3600)}h ago"
    return f"{int(delta/86400)}d ago"


def main() -> int:
    print()
    print("=" * 60)
    print("  GEPA chain status (Stages 1-7)")
    print("=" * 60)

    # Stage 1-3: compile state
    print()
    print("[Stage 1-3] dspy + GEPA compile")
    print("-" * 40)
    print(f"  DSPY_OPTIMIZER_ENABLED      = {os.environ.get('DSPY_OPTIMIZER_ENABLED', '(unset)')!r}")
    print(f"  GEMMA_AGENT_COUNCIL_ENABLED = {os.environ.get('GEMMA_AGENT_COUNCIL_ENABLED', '(unset)')!r}")
    print(f"  OLLAMA_HOST                 = {os.environ.get('OLLAMA_HOST', '(default)')!r}")
    report = _load_json(GEPA_REPORT)
    if report is None:
        print(f"  report file: {GEPA_REPORT.relative_to(REPO)}: (not present)")
    else:
        status = report.get("status", "?")
        ts = report.get("ran_at_ts", 0)
        elapsed = report.get("elapsed_s", 0)
        ms = report.get("metric_stats", {})
        print(f"  report status:    {status} ({_format_age(ts)})")
        print(f"  elapsed:          {elapsed:.1f}s")
        if status == "stage_3_compile_suspect":
            print(f"  ⚠ SUSPECT — operator should investigate before promoting")
            print(f"    metric_calls={ms.get('calls', 0)}, "
                  f"empty_answers={ms.get('empty_answers', 0)}, "
                  f"prompt_changed={report.get('prompt_changed', False)}")
        elif status == "stage_3_compiled":
            print(f"  ✓ ready for Stage-4 promotion")
            print(f"    predictors tuned: {len(report.get('optimized_prompts', {}))}")
            print(f"    metric_calls={ms.get('calls', 0)}, "
                  f"errors={ms.get('errors', 0)}")

    # Stage 4: promotion gate
    print()
    print("[Stage 4] promotion gate")
    print("-" * 40)
    print(f"  GEPA_PROMOTION_GATE_ENABLED = {os.environ.get('GEPA_PROMOTION_GATE_ENABLED', '(unset)')!r}")
    total, promoted, rejected = _load_jsonl_count(GEPA_HISTORY)
    print(f"  history rows:     {total} (promoted: {promoted}, rejected: {rejected})")
    if total == 0:
        print(f"  → gate has never run; run promote_gepa_prompts.py after compile")

    # Stage 5: overlay artifact
    print()
    print("[Stage 5] active-prompts overlay artifact")
    print("-" * 40)
    print(f"  GEPA_PROMPT_LOADER_ENABLED  = {os.environ.get('GEPA_PROMPT_LOADER_ENABLED', '(unset)')!r}")
    active = _load_json(GEPA_ACTIVE)
    if active is None:
        print(f"  artifact: {GEPA_ACTIVE.relative_to(REPO)}: (not present)")
        print(f"  → run Stage-4 gate first (promote_gepa_prompts.py)")
    else:
        ts = active.get("promoted_at_ts", 0)
        print(f"  artifact:         present ({_format_age(ts)})")
        print(f"  predictors:       {active.get('predictors_count', 0)}")
        print(f"  source LM:        {active.get('lm_model', '?')}")
        print(f"  GEPA elapsed:     {active.get('gepa_elapsed_s', 0):.1f}s")
        target = active.get("gepa_target_prompt")
        if target:
            print(f"  target prompt:    {target!r} (Path-B alias active)")
        else:
            print(f"  target prompt:    (none — predictor namespace only)")

    # Stage 6: Path-B alignment
    print()
    print("[Stage 6 Path-B] runtime-name alignment")
    print("-" * 40)
    print(f"  GEPA_TARGET_PROMPT_NAME     = {os.environ.get('GEPA_TARGET_PROMPT_NAME', '(unset)')!r}")
    if active and active.get("gepa_target_prompt"):
        print(f"  artifact carries target:   {active['gepa_target_prompt']!r}")
    else:
        print(f"  → set GEPA_TARGET_PROMPT_NAME=rag.qa before next compile")

    # Stage 7: canary routing
    print()
    print("[Stage 7] canary routing in rag_inference.ask")
    print("-" * 40)
    canary_enabled = os.environ.get("GEPA_CANARY_ENABLED", "").strip() == "1"
    canary_pct = os.environ.get("GEPA_CANARY_PERCENT", "0")
    print(f"  GEPA_CANARY_ENABLED         = {canary_enabled}")
    print(f"  GEPA_CANARY_PERCENT         = {canary_pct}")
    if not canary_enabled:
        print(f"  → canary OFF; all traffic on baseline")
    elif int(canary_pct or 0) == 0:
        print(f"  → canary enabled but percent=0; all traffic on baseline")
    else:
        print(f"  → routing ~{canary_pct}% of tenants to GEPA version")

    # Overall verdict
    print()
    print("=" * 60)
    if active and active.get("gepa_target_prompt") and canary_enabled and int(canary_pct or 0) > 0:
        print("  Overall: GEPA canary ROUTING (some traffic on tuned prompts)")
    elif active:
        print("  Overall: artifact ready; canary OFF — operator can activate")
    elif report and report.get("status") == "stage_3_compiled":
        print("  Overall: compile succeeded; Stage-4 promotion gate not run yet")
    elif report:
        print("  Overall: compile produced a report but flagged SUSPECT")
    else:
        print("  Overall: no compile run yet — `make empirical-gepa-compile`")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
