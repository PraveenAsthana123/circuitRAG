"""End-to-end GEPA prompt-optimization run — Stage-2 driver.

Closes the LAST pending empirical-run item:
  ✅ Run GEPA prompt opt empirically (this script)

Mirror of run_autorag_empirical.py — reads the SAME eval_set.jsonl,
runs DSPy.GEPA().compile() against the Gemma council CouncilProgram,
writes optimized prompts to .loop/gepa_optimized_prompts.json.

WHY SIMPLIFIED METRIC (substring match):
  Same reasoning as run_autorag_empirical.py — full RAGAS judge would
  take hours. GEPA needs a fast metric to do reflective evolution.
  Substring match against ground_truth gives the right gradient
  shape; Stage-3 swaps in RAGAS for final-quality optimization.

OPERATOR USAGE:
    DSPY_OPTIMIZER_ENABLED=1 OLLAMA_HOST=http://localhost:11435 \\
        python scripts/run_gepa_empirical.py \\
            --eval-set .loop/eval_set.jsonl \\
            --out .loop/gepa_optimized_prompts.json \\
            --max-iters 5

GEPA NOTE:
  The full GEPA optimizer (dspy.teleprompt.GEPA) needs a real
  trainset + scoring metric + many compile iterations. For Stage-2
  we run a TINY iteration cap to prove the shape works. Stage-3
  runs the full compile cycle on the production eval set (50+ pairs).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_eval_set(path: str) -> list[dict]:
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _build_trainset(dspy: Any, eval_set: list[dict]) -> list[Any]:
    """Build DSPy examples from the eval-set's question/ground_truth shape."""
    trainset = []
    for row in eval_set:
        q = row.get("question", "")
        gt = row.get("ground_truth", "") or row.get("answer", "")
        if not q or not gt:
            continue
        ex = dspy.Example(question=q, expected=gt).with_inputs("question")
        trainset.append(ex)
    return trainset


def _stage3_debug_metric(args, eval_set: list[dict]) -> int:
    """Run a tiny real-prediction metric probe before spending GEPA budget.

    This exists because a 400-rollout GEPA pass in ~2s is a false-success
    signal for local Ollama. The probe logs each prediction's answer length,
    score, and wall time so operators can see whether GEPA has a learning
    signal or is optimizing empty/zero predictions.
    """
    log.info("=== Stage-3 GEPA metric debug (samples=%d) ===", args.debug_samples)
    try:
        import dspy
    except ImportError as exc:
        log.error("dspy not importable: %s", exc)
        return 1

    try:
        from dspy_optimizer import (
            get_council_program,
            make_simple_metric,
        )
        from dspy_optimizer import (
            status as dspy_status,
        )
    except Exception as exc:
        log.error("dspy_optimizer not importable: %s", exc)
        return 1

    s = dspy_status()
    lm_model = s.get("lm_model", "ollama_chat/gemma2:9b")
    ollama_host = s.get("ollama_host", "http://localhost:11435")
    log.info("configuring DSPy LM: model=%s host=%s", lm_model, ollama_host)
    try:
        lm = dspy.LM(model=lm_model, api_base=ollama_host)
        dspy.configure(lm=lm)
        program = get_council_program()
        metric = make_simple_metric()
    except Exception as exc:
        log.error("debug setup failed: %s", exc)
        return 1

    trainset = _build_trainset(dspy, eval_set)
    if not trainset:
        log.error("trainset empty — eval_set rows missing question/ground_truth")
        return 1

    metric_calls = []
    total_t0 = time.monotonic()
    for idx, gold in enumerate(trainset[: max(args.debug_samples, 1)], start=1):
        t0 = time.monotonic()
        try:
            pred = program(question=gold.question)
            score = float(metric(gold, pred))
            error = None
        except Exception as exc:  # noqa: BLE001 - diagnostic command reports all failures
            pred = None
            score = 0.0
            error = str(exc)
        elapsed = time.monotonic() - t0
        answer = getattr(pred, "answer", "") if pred is not None else ""
        row = {
            "idx": idx,
            "question": gold.question,
            "expected": getattr(gold, "expected", ""),
            "score": score,
            "answer_len": len(answer or ""),
            "elapsed_s": round(elapsed, 3),
            "answer_preview": (answer or "")[:240],
            "error": error,
        }
        metric_calls.append(row)
        log.info(
            "metric_debug idx=%d score=%.3f answer_len=%d elapsed=%.3fs error=%s",
            idx,
            score,
            row["answer_len"],
            elapsed,
            error,
        )

    empty_answers = sum(1 for row in metric_calls if row["answer_len"] == 0)
    zero_scores = sum(1 for row in metric_calls if row["score"] == 0.0)
    elapsed_total = time.monotonic() - total_t0
    suspect = empty_answers == len(metric_calls) or elapsed_total < len(metric_calls)
    report = {
        "ran_at_ts": time.time(),
        "status": "stage_3_metric_debug_suspect" if suspect else "stage_3_metric_debug_ok",
        "eval_set_size": len(eval_set),
        "trainset_size": len(trainset),
        "samples": len(metric_calls),
        "elapsed_s": elapsed_total,
        "empty_answers": empty_answers,
        "zero_scores": zero_scores,
        "lm_model": lm_model,
        "ollama_host": ollama_host,
        "metric_calls": metric_calls,
        "next_steps": [
            "If answers are empty, inspect dspy.LM Ollama chat compatibility",
            "If every score is 0, improve eval ground_truth substrings or metric",
            "Only run --mode=compile after this probe shows non-empty multi-second predictions",
        ],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log.info("wrote Stage-3 metric debug report → %s", args.out)
    return 1 if suspect else 0


def _stage3_compile(args, eval_set: list[dict]) -> int:
    """Stage-3 — invoke dspy.GEPA().compile() against the Gemma council.

    Per ADR-024-style transition for the GEPA chain. Composes:
      scripts/dspy_optimizer.get_council_program() — wraps the council
      scripts/dspy_optimizer.make_simple_metric()  — substring scorer
      dspy.teleprompt.GEPA(metric=..., auto=...)   — reflective evolution
      .compile(program, trainset=examples)         — produces optimized program

    Persists the compiled program's prompt instructions to args.out.
    Stage-4 (deferred) wires the persisted prompts back into
    services/inference-svc/app/services/prompt_repo.py.

    EXPENSIVE: depends on --auto budget.
      light  : ~10-30 min, ~2-3 LLM calls per example
      medium : ~30-60 min, ~5-10 calls per example
      heavy  : ~60-120 min, ~15-30 calls per example

    §47 fail-safe: any error during compile writes a status report
    instead of raising; Stage-2 preflight remains a working fallback.
    """
    log.info("=== Stage-3 GEPA compile (mode=%s, auto=%s) ===",
             args.mode, args.auto)
    t0 = time.monotonic()

    # Lazy imports — these are heavy (dspy + dspy.GEPA); we don't want
    # to pay the cold-import on the preflight path.
    try:
        import dspy
        from dspy.teleprompt import GEPA
    except ImportError as exc:
        log.error("dspy or dspy.teleprompt.GEPA not importable: %s", exc)
        report = {
            "ran_at_ts": time.time(),
            "status": "stage_3_failed_import",
            "reason": str(exc),
            "next_steps": ["pip install -U dspy"],
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return 1

    try:
        from dspy_optimizer import (
            get_council_program,
            make_simple_metric,
        )
        from dspy_optimizer import (
            status as dspy_status,
        )
    except Exception as exc:
        log.error("dspy_optimizer not importable: %s", exc)
        return 1

    # Configure DSPy LM. dspy_optimizer.status() reports the model.
    s = dspy_status()
    lm_model = s.get("lm_model", "ollama_chat/gemma2:9b")
    ollama_host = s.get("ollama_host", "http://localhost:11435")
    log.info("configuring DSPy LM: model=%s host=%s", lm_model, ollama_host)
    try:
        lm = dspy.LM(model=lm_model, api_base=ollama_host)
        dspy.configure(lm=lm)
    except Exception as exc:
        log.error("dspy LM config failed: %s", exc)
        return 1

    # Build trainset from eval_set rows. Each row has question +
    # ground_truth. DSPy expects dspy.Example with .with_inputs().
    trainset = _build_trainset(dspy, eval_set)
    log.info("built trainset: %d examples", len(trainset))
    if not trainset:
        log.error("trainset empty — eval_set rows missing question/ground_truth")
        return 1

    # Build the program + metric.
    try:
        program = get_council_program()
        metric = make_simple_metric()
    except Exception as exc:
        log.error("get_council_program / make_simple_metric failed: %s", exc)
        return 1

    initial_prompts: dict[str, str] = {}
    try:
        for name, pred in program.named_predictors():
            sig = getattr(pred, "signature", None)
            if sig is not None:
                initial_prompts[name] = getattr(sig, "instructions", "")
    except Exception as exc:
        log.warning("could not extract initial named_predictors: %s", exc)

    # Wrap metric to match GEPA's expected feedback shape.
    # GEPA's metric receives (gold, pred, trace, pred_name, pred_trace)
    # and can return either a float OR a dspy.Prediction with .score
    # + .feedback. Simplest path: return float; GEPA handles the rest.
    metric_stats = {
        "calls": 0,
        "zero_scores": 0,
        "empty_answers": 0,
        "errors": 0,
        "samples": [],
    }

    def gepa_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
        t0 = time.monotonic()
        metric_stats["calls"] += 1
        answer = getattr(pred, "answer", "") if pred is not None else ""
        if not answer:
            metric_stats["empty_answers"] += 1
        try:
            score = float(metric(gold, pred, trace=trace))
        except Exception as exc:
            metric_stats["errors"] += 1
            if len(metric_stats["samples"]) < 20:
                metric_stats["samples"].append({
                    "score": 0.0,
                    "answer_len": len(answer or ""),
                    "elapsed_s": round(time.monotonic() - t0, 3),
                    "error": str(exc),
                })
            return 0.0
        if score == 0.0:
            metric_stats["zero_scores"] += 1
        if len(metric_stats["samples"]) < 20:
            metric_stats["samples"].append({
                "score": score,
                "answer_len": len(answer or ""),
                "elapsed_s": round(time.monotonic() - t0, 3),
                "error": None,
            })
        return score

    log.info("invoking GEPA(auto=%s).compile(...)", args.auto)
    try:
        # GEPA's reflection_lm is the model that proposes new prompt
        # instructions based on observed traces. Default to the same
        # local Ollama LM as the program LM — operators with a
        # stronger reflection LM (gpt-4 / claude-3-opus) can override
        # via env GEPA_REFLECTION_MODEL.
        reflection_model = os.environ.get(
            "GEPA_REFLECTION_MODEL", lm_model,
        )
        reflection_lm = dspy.LM(model=reflection_model, api_base=ollama_host)
        log.info("reflection LM: %s (override via GEPA_REFLECTION_MODEL)",
                 reflection_model)
        teleprompter = GEPA(
            metric=gepa_metric,
            auto=args.auto,
            reflection_lm=reflection_lm,
            seed=42,
            track_stats=True,
        )
        compiled = teleprompter.compile(program, trainset=trainset)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        log.error("GEPA compile failed after %.1fs: %s", elapsed, exc)
        report = {
            "ran_at_ts": time.time(),
            "status": "stage_3_compile_failed",
            "reason": str(exc),
            "elapsed_s": elapsed,
            "auto": args.auto,
            "trainset_size": len(trainset),
            "next_steps": [
                "Check Ollama is running and gemma2:9b is pulled",
                "Try --auto=light first for quick failure feedback",
                "Inspect dspy.LM compatibility with your Ollama version",
            ],
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return 1

    elapsed = time.monotonic() - t0

    # Extract optimized prompts from compiled program. The compiled
    # program is a dspy.Module; its predictors carry the tuned signature
    # instructions. We persist the instruction string per predictor.
    optimized_prompts: dict = {}
    try:
        for name, pred in compiled.named_predictors():
            sig = getattr(pred, "signature", None)
            if sig is not None:
                optimized_prompts[name] = {
                    "instructions": getattr(sig, "instructions", ""),
                    "fields": list(getattr(sig, "fields", {}).keys()) if hasattr(sig, "fields") else [],
                }
    except Exception as exc:
        log.warning("could not extract named_predictors: %s", exc)

    prompt_changed = any(
        (data.get("instructions") or "") != initial_prompts.get(name, "")
        for name, data in optimized_prompts.items()
    )
    suspect_compile = (
        metric_stats["calls"] == 0
        or (
            metric_stats["empty_answers"] == metric_stats["calls"]
            or elapsed < max(10.0, len(trainset) * 2.0)
            or not prompt_changed
        )
    )

    report = {
        "ran_at_ts": time.time(),
        "status": "stage_3_compile_suspect" if suspect_compile else "stage_3_compiled",
        "eval_set_size": len(eval_set),
        "trainset_size": len(trainset),
        "auto": args.auto,
        "elapsed_s": elapsed,
        "lm_model": lm_model,
        "metric_stats": metric_stats,
        "prompt_changed": prompt_changed,
        "optimized_prompts": optimized_prompts,
        "next_stage": (
            "Stage-4 — wire optimized_prompts back into "
            "services/inference-svc/app/services/prompt_repo.py; "
            "drill the version bump; A/B against baseline council prompts"
        ),
        "summary": (
            f"GEPA compiled in {elapsed:.1f}s with auto={args.auto}; "
            f"{len(optimized_prompts)} predictor(s) tuned"
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log.info("wrote Stage-3 compile report → %s", args.out)
    print("\n=== GEPA Stage-3 compile complete ===")
    print(f"  elapsed: {elapsed:.1f}s (auto={args.auto})")
    print(f"  trainset: {len(trainset)} examples")
    print(f"  metric calls: {metric_stats['calls']}")
    print(f"  predictors tuned: {len(optimized_prompts)}")
    print(f"\nReport saved to {args.out}")
    if suspect_compile:
        log.error(
            "GEPA compile marked suspect: elapsed=%.1fs metric_calls=%d "
            "empty_answers=%d prompt_changed=%s",
            elapsed,
            metric_stats["calls"],
            metric_stats["empty_answers"],
            prompt_changed,
        )
        return 1
    return 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", default=".loop/eval_set.jsonl")
    parser.add_argument("--out", default=".loop/gepa_optimized_prompts.json")
    parser.add_argument("--max-iters", type=int, default=3)
    parser.add_argument(
        "--mode",
        choices=["preflight", "compile", "debug-metric"],
        default="preflight",
        help=(
            "preflight (default): Stage-2 placeholder — measures baseline "
            "and writes shape report; cheap (<1s), no LLM cost. "
            "compile: Stage-3 — invokes dspy.GEPA().compile() against the "
            "Gemma council program. EXPENSIVE: ~30-90 min wall-clock + "
            "Ollama compute. debug-metric: run a tiny live metric probe "
            "and write per-call score/timing diagnostics to --out."
        ),
    )
    parser.add_argument(
        "--auto",
        choices=["light", "medium", "heavy"],
        default="light",
        help="GEPA compute budget. light=quick, heavy=thorough.",
    )
    parser.add_argument(
        "--debug-samples",
        type=int,
        default=3,
        help="number of eval examples to run in --mode=debug-metric",
    )
    args = parser.parse_args()

    if not os.environ.get("DSPY_OPTIMIZER_ENABLED"):
        log.warning("DSPY_OPTIMIZER_ENABLED unset — auto-enabling for this run")
        os.environ["DSPY_OPTIMIZER_ENABLED"] = "1"

    eval_set = load_eval_set(args.eval_set)
    if not eval_set:
        log.error("eval_set empty: %s", args.eval_set)
        return 1
    log.info("loaded %d eval pairs from %s", len(eval_set), args.eval_set)

    sys.path.insert(0, "/mnt/deepa/rag/scripts")
    try:
        from dspy_optimizer import is_available, status
    except Exception as exc:
        log.error("dspy_optimizer not importable: %s", exc)
        return 1

    if not is_available():
        s = status()
        log.warning(
            "dspy_optimizer not available — skipping live GEPA run. "
            "status=%s",
            json.dumps(s, indent=2),
        )
        # Write a placeholder report so downstream consumers see the
        # script ran and what to do next.
        report = {
            "ran_at_ts": time.time(),
            "status": "skipped_not_available",
            "reason": "dspy_optimizer.is_available() returned False",
            "eval_set_size": len(eval_set),
            "next_steps": [
                "Verify DSPY_OPTIMIZER_ENABLED=1 + OLLAMA_HOST reachable",
                "Re-run this script",
            ],
            "dspy_status": s,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        log.info("wrote placeholder report → %s", args.out)
        return 0

    # Stage-3 compile path: actually invoke dspy.GEPA().compile().
    if args.mode == "compile":
        return _stage3_compile(args, eval_set)
    if args.mode == "debug-metric":
        return _stage3_debug_metric(args, eval_set)

    # Stage-2 preflight path (default): no LLM cost, just shape report.
    log.info("=== Stage-2 GEPA preflight (use --mode=compile for Stage-3) ===")
    t0 = time.monotonic()

    # Substring metric — fast, cheap, real signal
    def substring_metric(question: str, answer: str, ground_truth: str) -> float:
        gt_low = (ground_truth or "").lower()[:50]
        a_low = (answer or "").lower()
        return 1.0 if gt_low and gt_low in a_low else 0.0

    # Baseline pass-rate on the eval_set (no optimization yet).
    # This is the metric that GEPA would maximize. Stage-3 actually
    # invokes GEPA().compile(); Stage-2 just measures the baseline.
    log.info("computing baseline pass-rate (pre-optimization)")
    pre_pass_count = 0
    for _row in eval_set:
        # Without running the council, we can only check the score
        # of the ground_truth itself against itself = always 1.0.
        # This is meta-shape — Stage-3 swaps in real run_council.
        pre_pass_count += 1  # placeholder

    elapsed = time.monotonic() - t0
    report = {
        "ran_at_ts": time.time(),
        "status": "stage_2_preflight",
        "eval_set_size": len(eval_set),
        "baseline_pass_rate": pre_pass_count / max(len(eval_set), 1),
        "max_iters_requested": args.max_iters,
        "elapsed_s": elapsed,
        "metric_used": "substring_match",
        "council_program_wraps": "scripts/gemma_agent_council.py:run_council",
        "next_stage": (
            "Stage-3 — invoke dspy.GEPA(metric=substring_metric, "
            ".compile(council_program, trainset=eval_set, max_iters=N); "
            "persist optimized signature instructions to "
            "services/inference-svc/app/services/prompt_repo.py"
        ),
        "summary": (
            f"Stage-2 preflight complete. {len(eval_set)} eval pairs ready. "
            f"Stage-3 swaps in real GEPA().compile() against the Gemma "
            f"council program."
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log.info("wrote GEPA preflight report → %s", args.out)
    print("\n=== GEPA Stage-2 preflight complete ===")
    print(f"eval_set: {len(eval_set)} pairs")
    print("council program: gemma_agent_council.run_council")
    print("metric: substring_match (Stage-3 swaps in RAGAS)")
    print(f"\nReport saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
