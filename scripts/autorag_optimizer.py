"""AutoRAG optimizer — Stage-1 adapter (per CLAUDE.md §56).

Closes the OPTIMIZATION-PLANE gap: this stack has 11 Stage-1/2 adapters
with knobs (min_score, chunking strategy, rerank top_k, council
thresholds, etc.) but no empirical search over the config space.
AutoRAG runs RAGAS metrics across a parameter grid and tells you
which config is empirically best on YOUR corpus.

WHY THIS SHAPE (composes with what's already shipped):
    Search axes come from existing Stage-1 adapters (operator can
    extend without modifying this module):
      - chunking_strategy_selector.choose() → 23 strategies
      - bge_reranker_protected.protected_rerank() → BGE on/off
      - HybridRetriever.RetrieveRequest.min_score → 0.0-1.0
      - HybridRetriever.RetrieveRequest.top_k → 5-50
      - gemma_agent_council models per role → A/B variants

    Metric function comes from ragas_eval_adapter.score():
      - faithfulness, answer_relevancy, context_precision,
        context_recall, answer_correctness
      - aggregated via AssessmentMatrix.overall_pass

    AutoRAG search loop:
      For each config in product(search_axes):
          for each (Q, A_ref, contexts_ref) in eval_set:
              answer = run_rag(Q, config)
              matrix = ragas_score(Q, answer, ctx, A_ref)
          aggregate matrices → BenchmarkMatrix
      Return config_ranked_by_overall_pass_rate

Stage-1 ships the SEARCH ENGINE; Stage-2 wires the eval set + runs
the search; Stage-3 commits the empirical best config to a registry.

OPERATOR OPT-IN:
    AUTORAG_OPTIMIZER_ENABLED=1
    OLLAMA_HOST=http://localhost:11435    # local-only

COMPOSES WITH (per §49):
    scripts/chunking_strategy_selector.py — chunking axis
    services/retrieval-svc/app/services/bge_reranker_protected.py — BGE on/off
    scripts/ragas_eval_adapter.py — metric function
    scripts/dspy_optimizer.py — orthogonal (prompts vs configs)
    docs/architecture/six-plane-audit-2026-05-04.md — Optimization Plane
    §38, §39, §43, §47, §48, §52, §56
"""
from __future__ import annotations

import itertools
import logging
import os
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

AUTORAG_OPTIMIZER_ENABLED = os.getenv("AUTORAG_OPTIMIZER_ENABLED", "").strip() == "1"


class AutoRAGOptimizerDisabled(RuntimeError):
    """Raised when search is invoked but env flag is unset."""


@dataclass
class ConfigPoint:
    """One point in the search space — a tuple of knobs."""
    chunking_strategy: str = "recursive_paragraph_sentence"
    min_score: float = 0.0
    rerank_enabled: bool = False
    rerank_top_k: int = 10
    retrieval_top_k: int = 10
    extra: dict[str, Any] = field(default_factory=dict)

    def signature(self) -> str:
        """Stable string key for caching + dedup in the search loop."""
        return (
            f"chunk={self.chunking_strategy}|"
            f"min_score={self.min_score}|"
            f"rerank={self.rerank_enabled}|"
            f"rerank_k={self.rerank_top_k}|"
            f"retrieve_k={self.retrieval_top_k}"
        )


@dataclass
class SearchAxes:
    """The set of knob ranges to search over."""
    chunking_strategies: list[str] = field(default_factory=lambda: [
        "recursive_paragraph_sentence",
        "layout_section_page_aware",
        "heading_codeblock_aware",
        "schema_plus_row_group",
    ])
    min_scores: list[float] = field(default_factory=lambda: [0.0, 0.3, 0.5, 0.7])
    rerank_options: list[bool] = field(default_factory=lambda: [False, True])
    retrieval_top_ks: list[int] = field(default_factory=lambda: [5, 10, 20])

    def grid_size(self) -> int:
        return (
            len(self.chunking_strategies)
            * len(self.min_scores)
            * len(self.rerank_options)
            * len(self.retrieval_top_ks)
        )

    def points(self):
        for chunk in self.chunking_strategies:
            for ms in self.min_scores:
                for rerank in self.rerank_options:
                    for k in self.retrieval_top_ks:
                        yield ConfigPoint(
                            chunking_strategy=chunk,
                            min_score=ms,
                            rerank_enabled=rerank,
                            retrieval_top_k=k,
                            rerank_top_k=min(k, 10),
                        )


@dataclass
class ConfigResult:
    """Per-config search result — score aggregated over the eval set."""
    config: ConfigPoint
    overall_pass_rate: float = 0.0
    per_metric_mean: dict[str, float] = field(default_factory=dict)
    eval_set_size: int = 0
    elapsed_s: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class SearchReport:
    """Final search output — best config + ranked list."""
    best_config: ConfigPoint | None = None
    best_pass_rate: float = 0.0
    ranked_configs: list[ConfigResult] = field(default_factory=list)
    grid_size: int = 0
    eval_set_size: int = 0
    total_elapsed_s: float = 0.0
    summary: str = ""


def is_env_enabled() -> bool:
    """Pure env-flag check — used to gate search_config_space.

    The custom search loop in this module is implemented in pure
    Python and DOES NOT call into the autorag package's runtime.
    Operator opt-in via env flag is the binding gate; package
    install is informational (see is_package_installed()).

    This split exists because autorag (as of 2026-05-05) pins
    matplotlib<3.7 which uses configparser.SafeConfigParser, removed
    in Python 3.12+. Forcing autorag-package-installed would block
    every operator on Python 3.13 from running their own empirical
    search — a §47 fail-safe contradiction.
    """
    return AUTORAG_OPTIMIZER_ENABLED


def is_package_installed() -> bool:
    """Probe whether the autorag PyPI package is importable.
    Informational only — search_config_space does NOT require it.
    Drives the §56 Gate-4 'empirical install verification' surface
    in status(); operators can see whether they completed the full
    techstack adoption regardless of whether the search runs.
    """
    try:
        import autorag  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def is_available() -> bool:
    """Backward-compatible alias for is_env_enabled().

    Historically this returned True only when both env flag AND
    package install were satisfied. As of 2026-05-05 the search
    loop has been verified to NOT use autorag's runtime, so the
    gate is reduced to env-flag-only. Operators reading status()
    still see is_package_installed in a separate field.
    """
    return is_env_enabled()


def status() -> dict[str, Any]:
    """Operator status surface."""
    out: dict[str, Any] = {
        "stage": 1,
        "enabled_env": AUTORAG_OPTIMIZER_ENABLED,
        "available": is_available(),
        "package_installed": is_package_installed(),
        "default_search_axes": SearchAxes().grid_size(),
        "composes_with": [
            "scripts/chunking_strategy_selector.py",
            "services/retrieval-svc/app/services/bge_reranker_protected.py",
            "scripts/ragas_eval_adapter.py",
        ],
        "wiring_status": "stage-1 search engine; Stage-2 wires eval_set + runs search; Stage-3 commits best config",
        "next_stage": (
            "Stage-2 — curate eval_set from BBC corpus + ground-truth Q&A; "
            "run search_config_space() with run_rag callback wired to "
            "HybridRetriever + Gemma council; persist SearchReport to "
            ".loop/autorag_search.jsonl; promote best ConfigPoint "
            "to inference-svc config registry"
        ),
    }
    if is_package_installed():
        try:
            import autorag
            out["autorag_version"] = getattr(autorag, "__version__", "unknown")
        except Exception as exc:
            out["autorag_probe_error"] = str(exc)
    return out


def search_config_space(
    *,
    eval_set: list[dict[str, Any]],
    run_rag: Callable[[str, ConfigPoint], dict[str, Any]],
    score_fn: Callable[[str, str, list[str], str | None], dict[str, Any]] | None = None,
    axes: SearchAxes | None = None,
    max_configs: int | None = None,
) -> SearchReport:
    """Empirical search over the parameter grid.

    Args:
        eval_set: list of dicts with keys 'question', 'ground_truth' (optional)
        run_rag: callback that takes (question, ConfigPoint) and returns
            dict with 'answer' + 'contexts' (list[str]). Caller wires this
            to HybridRetriever + Gemma council.
        score_fn: callback returning RAGAS-shape AssessmentMatrix dict.
            When None, uses ragas_eval_adapter.score() lazily.
        axes: SearchAxes to scan; default = SearchAxes().
        max_configs: optional cap on grid size (for smoke runs).

    Returns:
        SearchReport with best_config + ranked_configs.

    Raises:
        AutoRAGOptimizerDisabled: when env flag unset.
    """
    if not is_env_enabled():
        raise AutoRAGOptimizerDisabled(
            "AutoRAG optimizer disabled. Set AUTORAG_OPTIMIZER_ENABLED=1. "
            "(autorag package install is OPTIONAL — search loop is pure-Python; "
            "see is_package_installed() if you want the §56 Gate-4 status.)"
        )
    import time

    axes = axes or SearchAxes()
    if score_fn is None:
        # Lazy default — point at the RAGAS adapter shipped this session
        import sys
        sys.path.insert(0, "/mnt/deepa/rag/scripts")
        from ragas_eval_adapter import score as _ragas_score  # noqa: PLC0415

        def score_fn(q, a, ctx, gt):
            matrix = _ragas_score(question=q, answer=a, contexts=ctx, ground_truth=gt)
            return matrix.as_dict()

    t_total = time.monotonic()
    results: list[ConfigResult] = []
    points = list(axes.points())
    if max_configs is not None:
        points = points[:max_configs]

    for cp in points:
        t_cfg = time.monotonic()
        per_q_passes: list[bool] = []
        per_metric_vals: dict[str, list[float]] = {}

        for ex in eval_set:
            try:
                rag_out = run_rag(ex["question"], cp)
                answer = rag_out.get("answer", "")
                contexts = rag_out.get("contexts", [])
                gt = ex.get("ground_truth")
                matrix_d = score_fn(ex["question"], answer, contexts, gt)
                per_q_passes.append(bool(matrix_d.get("overall_pass", False)))
                for m, s in (matrix_d.get("scores") or {}).items():
                    per_metric_vals.setdefault(m, []).append(float(s))
            except Exception as exc:
                log.warning(
                    "autorag_search_skip_q config=%s q=%.40s err=%s",
                    cp.signature(), ex.get("question", "?"), exc,
                )

        if not per_q_passes:
            results.append(ConfigResult(
                config=cp,
                eval_set_size=len(eval_set),
                elapsed_s=time.monotonic() - t_cfg,
                skipped=True,
                skip_reason="all queries errored",
            ))
            continue

        pass_rate = sum(per_q_passes) / max(len(per_q_passes), 1)
        per_metric_mean = {
            m: statistics.mean(vals) if vals else 0.0
            for m, vals in per_metric_vals.items()
        }
        results.append(ConfigResult(
            config=cp,
            overall_pass_rate=pass_rate,
            per_metric_mean=per_metric_mean,
            eval_set_size=len(eval_set),
            elapsed_s=time.monotonic() - t_cfg,
        ))
        log.info(
            "autorag_search_config sig=%s pass_rate=%.2f elapsed=%.1fs",
            cp.signature(), pass_rate, time.monotonic() - t_cfg,
        )

    # Rank by pass-rate desc, then by mean of all metrics desc as tie-break
    def _rank_key(r: ConfigResult) -> tuple:
        if r.skipped:
            return (-1.0, 0.0)
        tie = statistics.mean(r.per_metric_mean.values()) if r.per_metric_mean else 0.0
        return (r.overall_pass_rate, tie)

    results.sort(key=_rank_key, reverse=True)
    best = results[0] if results and not results[0].skipped else None
    report = SearchReport(
        best_config=best.config if best else None,
        best_pass_rate=best.overall_pass_rate if best else 0.0,
        ranked_configs=results,
        grid_size=axes.grid_size(),
        eval_set_size=len(eval_set),
        total_elapsed_s=time.monotonic() - t_total,
    )
    if best:
        report.summary = (
            f"best={best.config.signature()} "
            f"pass_rate={best.overall_pass_rate:.2%} "
            f"({best.eval_set_size} questions, {len(results)} configs)"
        )
    else:
        report.summary = "no usable configs (all skipped)"
    return report


if __name__ == "__main__":
    import json
    import sys
    print("scripts/autorag_optimizer.py — Stage-1 AutoRAG empirical search")
    print(f"Stage-1 opt-in via AUTORAG_OPTIMIZER_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
