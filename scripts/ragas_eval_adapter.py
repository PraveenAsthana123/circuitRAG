"""RAGAS evaluation adapter — Stage-1 (per CLAUDE.md §56).

Closes the "Evaluation Plane" gap surfaced in
docs/architecture/six-plane-audit-2026-05-04.md: RAGAS was pip-installed
but eval-svc imports stayed `# noqa: F401` stubs. Stage-1 ships the
adapter + AssessmentMatrix dataclass; Stage-2 wires into eval-svc.

5 RAGAS metrics covered:
  - faithfulness         — answer grounded in retrieved contexts
  - answer_relevancy     — answer addresses the question
  - context_precision    — retrieved chunks are on-topic
  - context_recall       — retrieved chunks cover the ground truth
  - answer_correctness   — semantic + factual correctness vs reference

THE RAG ASSESSMENT MATRIX (operator-supplied concept):
  Per-call scores aggregated into rolling-window matrix with
  pass/fail thresholds + drift signal. The matrix IS the evaluation
  plane's headline output — operator sees it on a dashboard, ops sees
  it on alerts, audit row references it for §38 + §48.

OPERATOR OPT-IN:
    RAGAS_EVAL_ENABLED=1
    RAGAS_LM_MODEL=ollama_chat/gemma2:9b      # judge model (default)
    OLLAMA_HOST=http://localhost:11435        # local-only
    RAGAS_FAITHFULNESS_THRESHOLD=0.7          # operator-tunable per-metric floors
    RAGAS_ANSWER_RELEVANCY_THRESHOLD=0.7
    RAGAS_CONTEXT_PRECISION_THRESHOLD=0.5
    RAGAS_CONTEXT_RECALL_THRESHOLD=0.5
    RAGAS_ANSWER_CORRECTNESS_THRESHOLD=0.6

COMPOSES WITH (per §49):
    services/evaluation-svc/app/eval_harness.py — Stage-2 wires score()
                                                  into the harness
    services/inference-svc/app/services/rag_inference.py — Stage-2 calls
                                                          score() per /ask
    .loop/ragas_eval_audit.jsonl — Stage-2 persists per-call scores
    docs/architecture/six-plane-audit-2026-05-04.md — Evaluation Plane
    §38 — decision audit (every score persisted)
    §39 — RAG architecture (continuous eval is § rule)
    §43 — drill discipline
    §47 — architecture (additive: Evaluation Plane stage-1)
    §48 — explainability (per-metric scores = evidence)
    §52 — brutal tool review (40-row when wired in inference hot path)
    §56 — Stage-1 6-gate adoption process
"""
from __future__ import annotations

import logging
import os
import statistics
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

RAGAS_EVAL_ENABLED = os.getenv("RAGAS_EVAL_ENABLED", "").strip() == "1"
RAGAS_LM_MODEL = os.getenv("RAGAS_LM_MODEL", "ollama_chat/gemma2:9b")
RAGAS_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Per-metric floors (operator-tunable). Below = fail; at-or-above = pass.
# Defaults reflect typical RAG production gates for hybrid retrieval +
# strong-LLM stacks. Tune per-corpus after baseline measurement.
THRESHOLDS = {
    "faithfulness":        float(os.getenv("RAGAS_FAITHFULNESS_THRESHOLD", "0.7")),
    "answer_relevancy":    float(os.getenv("RAGAS_ANSWER_RELEVANCY_THRESHOLD", "0.7")),
    "context_precision":   float(os.getenv("RAGAS_CONTEXT_PRECISION_THRESHOLD", "0.5")),
    "context_recall":      float(os.getenv("RAGAS_CONTEXT_RECALL_THRESHOLD", "0.5")),
    "answer_correctness":  float(os.getenv("RAGAS_ANSWER_CORRECTNESS_THRESHOLD", "0.6")),
}

# The 5 RAGAS metrics the adapter computes. Caller can subset via
# `metrics=` param to score(); useful when ground_truth is absent and
# answer_correctness can't be computed.
ALL_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
)


class RAGASEvalDisabled(RuntimeError):
    """Raised when score() is called but the env flag is unset."""


@dataclass
class AssessmentMatrix:
    """RAG ASSESSMENT MATRIX — per-call scores + pass/fail per threshold.

    Operator dashboards render `summary` for headline; alerts fire on
    `failures`; §38 audit row persists the full dataclass.
    """
    scores: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    passes: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    overall_pass: bool = False
    summary: str = ""
    metric_count: int = 0
    judge_model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scores": dict(self.scores),
            "thresholds": dict(self.thresholds),
            "passes": dict(self.passes),
            "failures": list(self.failures),
            "overall_pass": self.overall_pass,
            "summary": self.summary,
            "metric_count": self.metric_count,
            "judge_model": self.judge_model,
        }


@dataclass
class BenchmarkMatrix:
    """Aggregated rolling-window stats over many AssessmentMatrix rows.

    Caller persists per-call AssessmentMatrix to JSONL; eval-svc reads
    a window (e.g. last 24h) and builds a BenchmarkMatrix for the
    dashboard. §39 — continuous quality monitoring.
    """
    window_size: int = 0
    per_metric_mean: dict[str, float] = field(default_factory=dict)
    per_metric_p50: dict[str, float] = field(default_factory=dict)
    per_metric_p95: dict[str, float] = field(default_factory=dict)
    per_metric_pass_rate: dict[str, float] = field(default_factory=dict)
    overall_pass_rate: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_size": self.window_size,
            "per_metric_mean": dict(self.per_metric_mean),
            "per_metric_p50": dict(self.per_metric_p50),
            "per_metric_p95": dict(self.per_metric_p95),
            "per_metric_pass_rate": dict(self.per_metric_pass_rate),
            "overall_pass_rate": self.overall_pass_rate,
        }


def is_available() -> bool:
    """Stage-1 §56 default-deny + RAGAS install probe."""
    if not RAGAS_EVAL_ENABLED:
        return False
    try:
        import ragas  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator status surface — same shape as other Stage-1 adapters."""
    out: dict[str, Any] = {
        "stage": 1,
        "enabled_env": RAGAS_EVAL_ENABLED,
        "available": is_available(),
        "lm_model": RAGAS_LM_MODEL,
        "ollama_host": RAGAS_OLLAMA_HOST,
        "metrics": list(ALL_METRICS),
        "thresholds": dict(THRESHOLDS),
        "wiring_status": "stage-1 adapter; Stage-2 wires into eval_harness.py + rag_inference.py",
        "next_stage": (
            "Stage-2 — eval-svc imports score() into eval_harness.py; "
            "rag_inference.py calls score() after every /ask; per-call "
            "AssessmentMatrix persisted to .loop/ragas_eval_audit.jsonl; "
            "rolling BenchmarkMatrix on dashboard"
        ),
    }
    if is_available():
        try:
            import ragas
            out["ragas_version"] = ragas.__version__
        except Exception as exc:
            out["ragas_probe_error"] = str(exc)
    return out


def _configure_judge():
    """Wire RAGAS to use the local Ollama judge — no external API.

    RAGAS metrics need an LLM-as-judge. We point it at the same Gemma
    stack the council uses, keeping the eval plane fully local.
    """
    if not is_available():
        raise RAGASEvalDisabled(
            "RAGAS eval disabled. Set RAGAS_EVAL_ENABLED=1 and ensure "
            "ragas is installed."
        )
    # Lazy imports — keep cold-start fast for callers that don't need
    # the judge (e.g., status() probes don't load the LM).
    from langchain_community.chat_models import ChatOllama  # noqa: PLC0415
    from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415

    lm = ChatOllama(model=RAGAS_LM_MODEL.replace("ollama_chat/", ""),
                    base_url=RAGAS_OLLAMA_HOST)
    return LangchainLLMWrapper(lm)


def score(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
    metrics: tuple[str, ...] | None = None,
) -> AssessmentMatrix:
    """Compute RAGAS metrics for a single (Q, A, contexts) tuple.

    Args:
        question: the user query
        answer: the generated answer
        contexts: list of retrieved chunk texts
        ground_truth: optional reference answer; required for
            context_recall + answer_correctness; the other 3 metrics
            work without it
        metrics: subset of ALL_METRICS to compute; None = all that
            have inputs (auto-skips correctness/recall if no
            ground_truth)

    Returns:
        AssessmentMatrix with per-metric scores + pass/fail vs
        configured thresholds.

    Raises:
        RAGASEvalDisabled: when RAGAS_EVAL_ENABLED is unset or ragas
        is not installed.
    """
    if not is_available():
        raise RAGASEvalDisabled(
            "RAGAS eval disabled. Set RAGAS_EVAL_ENABLED=1 and ensure "
            "ragas is installed."
        )

    # Determine which metrics to run
    if metrics is None:
        metrics = ALL_METRICS
    selected = [m for m in metrics if m in ALL_METRICS]
    # Auto-drop metrics that need ground_truth when it's absent
    if ground_truth is None:
        selected = [m for m in selected
                    if m not in ("context_recall", "answer_correctness")]

    if not selected:
        return AssessmentMatrix(
            summary="no metrics selected (likely missing ground_truth)",
            judge_model=RAGAS_LM_MODEL,
        )

    # Lazy ragas import + eval
    from datasets import Dataset  # noqa: PLC0415
    from ragas import evaluate  # noqa: PLC0415
    from ragas.metrics import (  # noqa: PLC0415
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    metric_map = {
        "faithfulness":       faithfulness,
        "answer_relevancy":   answer_relevancy,
        "context_precision":  context_precision,
        "context_recall":     context_recall,
        "answer_correctness": answer_correctness,
    }
    metric_objs = [metric_map[m] for m in selected]

    judge = _configure_judge()
    for m in metric_objs:
        if hasattr(m, "llm"):
            m.llm = judge

    row: dict[str, Any] = {
        "question": [question],
        "answer": [answer],
        "contexts": [contexts],
    }
    if ground_truth is not None:
        row["ground_truth"] = [ground_truth]
    ds = Dataset.from_dict(row)

    try:
        result = evaluate(ds, metrics=metric_objs, llm=judge)
        scores_dict = {k: float(v) for k, v in result.items()
                       if k in selected}
    except Exception as exc:
        log.warning("ragas evaluate failed: %s", exc)
        return AssessmentMatrix(
            summary=f"evaluate-error: {type(exc).__name__}: {str(exc)[:120]}",
            judge_model=RAGAS_LM_MODEL,
        )

    matrix = AssessmentMatrix(
        scores=scores_dict,
        thresholds={k: THRESHOLDS[k] for k in selected if k in THRESHOLDS},
        judge_model=RAGAS_LM_MODEL,
        metric_count=len(selected),
    )
    for m, s in scores_dict.items():
        threshold = THRESHOLDS.get(m, 0.5)
        passed = s >= threshold
        matrix.passes[m] = passed
        if not passed:
            matrix.failures.append(m)
    matrix.overall_pass = len(matrix.failures) == 0
    matrix.summary = (
        f"{sum(matrix.passes.values())}/{len(matrix.passes)} metrics pass; "
        f"failures={matrix.failures or '[]'}"
    )

    log.info(
        "ragas_score q=%.50s ok=%s failures=%s",
        question, matrix.overall_pass, matrix.failures,
    )
    return matrix


def aggregate(rows: list[AssessmentMatrix]) -> BenchmarkMatrix:
    """Build a BenchmarkMatrix from a window of per-call AssessmentMatrix.

    Caller reads .loop/ragas_eval_audit.jsonl, deserializes into
    AssessmentMatrix list, passes here. Returns rolling-window stats.
    """
    if not rows:
        return BenchmarkMatrix(window_size=0)

    by_metric: dict[str, list[float]] = {}
    pass_count = 0
    for r in rows:
        if r.overall_pass:
            pass_count += 1
        for m, s in r.scores.items():
            by_metric.setdefault(m, []).append(s)

    bench = BenchmarkMatrix(
        window_size=len(rows),
        overall_pass_rate=pass_count / max(len(rows), 1),
    )
    for m, vals in by_metric.items():
        if not vals:
            continue
        bench.per_metric_mean[m] = statistics.mean(vals)
        bench.per_metric_p50[m] = statistics.median(vals)
        sorted_vals = sorted(vals)
        bench.per_metric_p95[m] = sorted_vals[int(len(sorted_vals) * 0.95)]
        threshold = THRESHOLDS.get(m, 0.5)
        passes = sum(1 for v in vals if v >= threshold)
        bench.per_metric_pass_rate[m] = passes / len(vals)
    return bench


if __name__ == "__main__":
    import json
    import sys
    print("scripts/ragas_eval_adapter.py — Stage-1 RAGAS evaluation adapter")
    print("Stage-1 opt-in via RAGAS_EVAL_ENABLED=1")
    print(f"Computes 5 metrics: {', '.join(ALL_METRICS)}")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
