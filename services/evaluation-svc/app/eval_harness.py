"""Stage-1 eval-harness — Ragas + Guardrails AI + DeepEval scaffolds.

Per the 11-layer architecture (Layer 10: Governance + Evaluation).
Stage-1 is import-safe: each engine is wrapped in try/except so the
service starts even if the eval libs aren't installed yet (during
the first deploy where the new deps haven't propagated).

Stage-2 wires these into the request path:
  - Guardrails AI as an output filter (every LLM response passes
    through before the user sees it)
  - Ragas as a periodic eval job (samples 1% of RAG queries, scores
    faithfulness + relevance + context-precision, alerts on drift)
  - DeepEval as an alternative RAG eval (run weekly for triangulation)

The CONTRACT in Stage-1: each engine exposes `is_available() -> bool`
+ `evaluate(...) -> dict`. Drill locks both surfaces. Stage-2 swaps
the dummy `evaluate` body to actually call the library — the contract
stays.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------- Ragas ---------- (Stage-1 scaffold)

class RagasEngine:
    """Wraps ragas.metrics for RAG evaluation. Stage-1: import-safe stub."""

    def __init__(self) -> None:
        self._ragas: Any = None
        try:
            import ragas  # noqa: F401
            self._ragas = ragas
            logger.info("ragas %s available", getattr(ragas, "__version__", "?"))
        except ImportError:
            logger.warning("ragas not installed; eval scaffold returns dummy results")

    def is_available(self) -> bool:
        return self._ragas is not None

    def evaluate(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> dict[str, Any]:
        """Score a RAG answer on faithfulness + relevance + context-precision.

        Stage-1 returns dummy scores when ragas is unavailable. Stage-2
        will call ragas.evaluate(dataset, metrics=[faithfulness, ...]).
        """
        if not self._ragas:
            return {
                "available": False,
                "reason": "ragas not installed",
                "stub": True,
            }
        # Stage-2 wire: delegate to scripts/ragas_eval_adapter.py so this
        # harness composes with the canonical Stage-1 adapter (5 metrics,
        # AssessmentMatrix shape, per-metric thresholds, audit-ready).
        # When the adapter is disabled or errors, fall back to the
        # stub shape so callers don't see a regression. Per §47 fail-safe.
        import os as _os  # noqa: PLC0415
        import sys as _sys  # noqa: PLC0415
        _sys.path.insert(0, "/mnt/deepa/rag/scripts")
        try:
            # Adapter requires its own env flag to be set, separate from
            # ragas being installed. If operator hasn't opted in, return
            # a clear reason so the dashboard shows "not configured" not
            # "not available".
            if _os.getenv("RAGAS_EVAL_ENABLED", "").strip() != "1":
                return {
                    "available": True,
                    "configured": False,
                    "reason": "RAGAS_EVAL_ENABLED unset",
                    "metrics": {
                        "faithfulness": None,
                        "answer_relevance": None,
                        "context_precision": None,
                        "context_recall": None,
                    },
                }
            from ragas_eval_adapter import score as _ragas_score  # noqa: PLC0415
            matrix = _ragas_score(
                question=question,
                answer=answer,
                contexts=contexts,
                ground_truth=ground_truth,
            )
            return {
                "available": True,
                "configured": True,
                # 'scores' is the canonical AssessmentMatrix field;
                # 'metrics' is the legacy alias for dashboard backward
                # compat. Both populated identically.
                "scores": dict(matrix.scores),
                "metrics": dict(matrix.scores),
                "thresholds": dict(matrix.thresholds),
                "passes": dict(matrix.passes),
                "failures": list(matrix.failures),
                "overall_pass": matrix.overall_pass,
                "summary": matrix.summary,
                "judge_model": matrix.judge_model,
                "input": {
                    "question": question[:80],
                    "answer_len": len(answer),
                    "context_count": len(contexts),
                    "has_ground_truth": ground_truth is not None,
                },
            }
        except Exception as _exc:
            # Per §47 fail-safe: never break the eval-svc on adapter
            # error. Return the stub shape with the error attached so
            # ops can see it without losing the request.
            logger.warning("ragas_adapter_error: %s", _exc)
            return {
                "available": True,
                "configured": True,
                "error": f"{type(_exc).__name__}: {str(_exc)[:200]}",
                "stub": True,
                "metrics": {
                    "faithfulness": None,
                    "answer_relevance": None,
                    "context_precision": None,
                    "context_recall": None,
                },
            }


# ---------- Guardrails AI ---------- (Stage-1 scaffold)

class GuardrailsEngine:
    """Wraps guardrails-ai for output validation + jailbreak defense.

    Stage-1: import-safe stub. Stage-2 wires this into the LLM
    response path so every output passes through Guardrails BEFORE
    the user sees it.
    """

    def __init__(self) -> None:
        self._guardrails: Any = None
        try:
            import guardrails as gd
            self._guardrails = gd
            logger.info("guardrails-ai %s available", getattr(gd, "__version__", "?"))
        except ImportError:
            logger.warning("guardrails-ai not installed; eval scaffold returns dummy results")

    def is_available(self) -> bool:
        return self._guardrails is not None

    def validate_output(
        self,
        *,
        text: str,
        validators: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run output validators (PII detection, jailbreak, toxic content).

        Stage-1 returns dummy results. Stage-2 will use Guard.from_string()
        with the configured validators.
        """
        if not self._guardrails:
            return {
                "available": False,
                "reason": "guardrails-ai not installed",
                "validation_passed": True,  # fail-open in Stage-1
                "stub": True,
            }
        return {
            "available": True,
            "stub": True,
            "validation_passed": True,
            "validators_run": validators or ["pii", "toxic", "jailbreak"],
            "violations": [],  # Stage-2 populates from real validator runs
            "input_len": len(text),
        }


# ---------- DeepEval ---------- (Stage-1 scaffold)

class DeepEvalEngine:
    """Wraps deepeval for alternative RAG evaluation. Stage-1 stub."""

    def __init__(self) -> None:
        self._deepeval: Any = None
        try:
            import deepeval  # noqa: F401
            self._deepeval = deepeval
            logger.info("deepeval %s available", getattr(deepeval, "__version__", "?"))
        except ImportError:
            logger.warning("deepeval not installed; eval scaffold returns dummy results")

    def is_available(self) -> bool:
        return self._deepeval is not None

    def evaluate(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> dict[str, Any]:
        if not self._deepeval:
            return {
                "available": False,
                "reason": "deepeval not installed",
                "stub": True,
            }
        return {
            "available": True,
            "stub": True,
            "metrics": {
                "answer_relevancy": None,
                "faithfulness": None,
                "contextual_precision": None,
                "contextual_recall": None,
            },
        }


# ---------- Aggregator ---------- (the public surface)

def eval_status() -> dict[str, Any]:
    """Operator-readable health check: which engines are wired?

    Used by /api/v1/evaluation/health and surfaced in the
    /admin/checklist deep-dive page.
    """
    ragas = RagasEngine()
    guardrails = GuardrailsEngine()
    deepeval = DeepEvalEngine()
    return {
        "stage": 1,
        "engines": {
            "ragas": {"available": ragas.is_available()},
            "guardrails": {"available": guardrails.is_available()},
            "deepeval": {"available": deepeval.is_available()},
        },
        "all_available": (
            ragas.is_available()
            and guardrails.is_available()
            and deepeval.is_available()
        ),
        "note": (
            "Stage-1 — engines stub their evaluate() method. Stage-2 "
            "wires real library calls. Stage-3 runs Ragas as a "
            "periodic eval job + Guardrails as an inline output filter."
        ),
    }
