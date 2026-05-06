#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Path-B operator escape valve for GEPA predictor-name alignment.

Per docs/architecture/gepa-chain-status-and-stage6-blocker.md, Path B
adds GEPA_TARGET_PROMPT_NAME env var support so the GEPA-tuned prompt
gets registered under the operator-declared runtime name (e.g. rag.qa)
in addition to the predictor namespace (predict.predict_gepa-<ts>).

This unblocks operator end-to-end testing without the larger Path A
refactor of CouncilProgram. Path A remains the long-term right answer.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "promote_gepa_prompts.py"
PROMPT_REPO = REPO / "services" / "inference-svc" / "app" / "services" / "prompt_repo.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("promote_gepa_prompts", GATE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["promote_gepa_prompts"] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def _make_report(tmp: Path, **overrides) -> Path:
    """Synthesize a passing GEPA report (default: all gates green)."""
    base = {
        "ran_at_ts": time.time(),
        "status": "stage_3_compiled",
        "eval_set_size": 5,
        "trainset_size": 5,
        "auto": "light",
        "elapsed_s": 120.0,
        "lm_model": "ollama_chat/gemma2:9b",
        "metric_stats": {
            "calls": 50, "zero_scores": 10, "empty_answers": 0,
            "errors": 0, "samples": [],
        },
        "prompt_changed": True,
        "optimized_prompts": {
            "predict.predict": {
                "instructions": "Answer the user's question using council reasoning.",
                "fields": ["question", "answer"],
            },
        },
    }
    base.update(overrides)
    p = tmp / "report.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def main() -> int:
    print("-- 1. POSITIVE: gate accepts target_prompt_name kwarg --")
    if not GATE.exists():
        print(f"x {GATE} missing")
        return 1
    src = GATE.read_text(encoding="utf-8")
    if "target_prompt_name: str | None = None" not in src:
        print("x promote() must accept target_prompt_name kwarg")
        return 1
    print("  ok: target_prompt_name kwarg declared")

    print("-- 2. POSITIVE: gate reads GEPA_TARGET_PROMPT_NAME env fallback --")
    if 'os.environ.get("GEPA_TARGET_PROMPT_NAME"' not in src:
        print("x gate must fallback to GEPA_TARGET_PROMPT_NAME env var")
        return 1
    print("  ok: env-var fallback present")

    print("-- 3. NEGATIVE: gate writes gepa_target_prompt field into artifact --")
    if '"gepa_target_prompt": resolved_target' not in src:
        print("x artifact must include gepa_target_prompt field")
        return 1
    print("  ok: artifact field declared")

    print("-- 4. POSITIVE: gate persists target name when kwarg passed --")
    os.environ["GEPA_PROMOTION_GATE_ENABLED"] = "1"
    os.environ.pop("GEPA_TARGET_PROMPT_NAME", None)
    mod, _ = _load_gate()
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p)
        active_path = tmp_p / "active.json"
        decision = mod.promote(
            report_path=str(report),
            active_path=str(active_path),
            history_path=str(tmp_p / "history.jsonl"),
            target_prompt_name="rag.qa",
        )
        if not decision.promoted:
            print(f"x valid report should promote; got {decision.reason}")
            return 1
        artifact = json.loads(active_path.read_text())
        if artifact.get("gepa_target_prompt") != "rag.qa":
            print(f"x artifact gepa_target_prompt expected 'rag.qa'; got {artifact.get('gepa_target_prompt')!r}")
            return 1
    print("  ok: kwarg threads into artifact")

    print("-- 5. POSITIVE: env var fallback works when kwarg omitted --")
    os.environ["GEPA_TARGET_PROMPT_NAME"] = "agent.intent_router"
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p)
        active_path = tmp_p / "active.json"
        decision = mod.promote(
            report_path=str(report),
            active_path=str(active_path),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if not decision.promoted:
            print(f"x valid report should promote; got {decision.reason}")
            return 1
        artifact = json.loads(active_path.read_text())
        if artifact.get("gepa_target_prompt") != "agent.intent_router":
            print(f"x env var fallback failed; got {artifact.get('gepa_target_prompt')!r}")
            return 1
    os.environ.pop("GEPA_TARGET_PROMPT_NAME", None)
    print("  ok: env var threads into artifact when kwarg omitted")

    print("-- 6. NEGATIVE: missing target → gepa_target_prompt is null (not crash) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p)
        active_path = tmp_p / "active.json"
        decision = mod.promote(
            report_path=str(report),
            active_path=str(active_path),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if not decision.promoted:
            print(f"x missing target should still promote; got {decision.reason}")
            return 1
        artifact = json.loads(active_path.read_text())
        if artifact.get("gepa_target_prompt") is not None:
            print(f"x missing target should yield None; got {artifact.get('gepa_target_prompt')!r}")
            return 1
    print("  ok: target=None tolerated; artifact carries None field")

    print("-- 7. NEGATIVE: prompt_repo overlay reads gepa_target_prompt + adds alias --")
    if not PROMPT_REPO.exists():
        print(f"x {PROMPT_REPO} missing")
        return 1
    repo_src = PROMPT_REPO.read_text(encoding="utf-8")
    if 'data.get("gepa_target_prompt")' not in repo_src:
        print("x overlay must read gepa_target_prompt from artifact")
        return 1
    if 'alias_key = f"{gepa_target}_{version_tag}"' not in repo_src:
        print("x overlay must register an alias under <gepa_target>_<version>")
        return 1
    if "if gepa_target and not any(" not in repo_src:
        print("x alias registration must be guarded by gepa_target presence + de-dup")
        return 1
    print("  ok: overlay registers alias under runtime target name")

    print("-- 8. POSITIVE: alias only fires for FIRST predictor (multi-predictor goes to Path A) --")
    # The Path-B alias is intentionally limited to single-predictor cases
    # (typical CouncilProgram has predict.predict only). Multi-predictor
    # outputs need per-predictor mapping which is Path A's design space.
    # Drill verifies the dedup guard exists.
    if "not any(" not in repo_src or "k.startswith(f\"{gepa_target}_gepa-\")" not in repo_src:
        print("x alias guard must skip if alias key already registered")
        return 1
    # And the docstring/comment must reference Path A boundary
    if "Path A" not in repo_src:
        print("x overlay must reference Path A as the multi-predictor escape")
        return 1
    print("  ok: Path-B aliasing scoped to single-predictor; Path A noted")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
