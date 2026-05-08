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
        self._import_error: str | None = None
        try:
            import ragas  # noqa: F401
            self._ragas = ragas
            logger.info("ragas %s available", getattr(ragas, "__version__", "?"))
        except Exception as exc:  # noqa: BLE001
            self._import_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning("ragas unavailable; eval scaffold returns stub results: %s", self._import_error)

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
                "reason": self._import_error or "ragas not installed",
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

        Stage-2: env-gated real invocation.
          GUARDRAILS_EVAL_ENABLED=1  → run Guard.from_string() with
                                       the configured validators
          GUARDRAILS_EVAL_ENABLED unset/0 → return 'configured: false'

        Per §47 fail-safe: any validator error returns the stub shape
        with the error attached so eval-svc never breaks user requests.
        """
        if not self._guardrails:
            return {
                "available": False,
                "reason": "guardrails-ai not installed",
                "validation_passed": True,  # fail-open in Stage-1
                "stub": True,
            }
        import os as _os  # noqa: PLC0415
        if _os.getenv("GUARDRAILS_EVAL_ENABLED", "").strip() != "1":
            return {
                "available": True,
                "configured": False,
                "reason": "GUARDRAILS_EVAL_ENABLED unset",
                "validation_passed": True,
                "validators_run": validators or ["pii", "toxic", "jailbreak"],
                "violations": [],
                "input_len": len(text),
            }
        try:
            # Stage-2 active. Call Guard.from_string() with the requested
            # validator subset; fall back to default trio when unset.
            requested = validators or ["pii", "toxic", "jailbreak"]
            gd = self._guardrails
            # The exact validator-name → class mapping varies across
            # guardrails versions; use the registry lookup so the
            # eval harness stays version-tolerant.
            validator_objs = []
            for vname in requested:
                try:
                    cls = getattr(gd, "validators", None)
                    if cls is not None and hasattr(cls, vname):
                        validator_objs.append(getattr(cls, vname)())
                except Exception as exc:  # noqa: BLE001 — version drift tolerant
                    logger.debug("guardrails_validator_lookup_failed %s: %s", vname, exc)
            guard = gd.Guard.from_string(validators=validator_objs)
            outcome = guard.parse(text)
            violations = []
            passed = True
            # Different guardrails versions surface validation outcome
            # under different attributes; probe a few.
            for attr in ("validation_passed", "passed", "is_valid"):
                if hasattr(outcome, attr):
                    passed = bool(getattr(outcome, attr))
                    break
            for attr in ("validation_summaries", "errors", "violations"):
                if hasattr(outcome, attr):
                    violations = list(getattr(outcome, attr) or [])
                    break
            return {
                "available": True,
                "configured": True,
                "validation_passed": passed,
                "validators_run": requested,
                "violations": [str(v)[:200] for v in violations],
                "input_len": len(text),
            }
        except Exception as _exc:  # noqa: BLE001
            logger.warning("guardrails_validate_error: %s", _exc)
            return {
                "available": True,
                "configured": True,
                "error": str(_exc)[:200],
                "validation_passed": True,  # fail-open per §47
                "validators_run": validators or ["pii", "toxic", "jailbreak"],
                "violations": [],
                "input_len": len(text),
            }


# ---------- DeepEval ---------- (Stage-1 scaffold)

class DeepEvalEngine:
    """Wraps deepeval for alternative RAG evaluation. Stage-1 stub."""

    def __init__(self) -> None:
        self._deepeval: Any = None
        self._import_error: str | None = None
        try:
            import ssl
            if not hasattr(ssl, "wrap_socket"):
                raise RuntimeError(
                    "deepeval import stack requires ssl.wrap_socket in this environment",
                )
            import deepeval  # noqa: F401
            from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric  # noqa: F401
            from deepeval.test_case import LLMTestCase  # noqa: F401
            self._deepeval = deepeval
            logger.info("deepeval %s available", getattr(deepeval, "__version__", "?"))
        except Exception as exc:  # noqa: BLE001
            self._import_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning("deepeval unavailable; eval scaffold returns stub results: %s", self._import_error)

    def is_available(self) -> bool:
        return self._deepeval is not None

    def evaluate(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> dict[str, Any]:
        """Score answer via deepeval. Stage-2: env-gated real invocation.

        DEEPEVAL_ENABLED=1 → run AnswerRelevancyMetric / FaithfulnessMetric
        unset/0          → return 'configured: false' shape

        Per §47 fail-safe: any metric error returns the stub shape with
        the error attached so eval-svc never breaks user requests.
        """
        if not self._deepeval:
            return {
                "available": False,
                "reason": self._import_error or "deepeval not installed",
                "stub": True,
            }
        import os as _os  # noqa: PLC0415
        if _os.getenv("DEEPEVAL_ENABLED", "").strip() != "1":
            return {
                "available": True,
                "configured": False,
                "reason": "DEEPEVAL_ENABLED unset",
                "metrics": {
                    "answer_relevancy": None,
                    "faithfulness": None,
                    "contextual_precision": None,
                    "contextual_recall": None,
                },
            }
        try:
            # deepeval imports moved between minor versions; probe both
            # known module paths so the harness is version-tolerant.
            try:
                from deepeval.metrics import (  # type: ignore[import-not-found]
                    AnswerRelevancyMetric,
                    FaithfulnessMetric,
                )
                from deepeval.test_case import LLMTestCase  # type: ignore[import-not-found]
            except ImportError:
                # Older deepeval 0.x layout
                from deepeval.metrics.answer_relevancy import (  # type: ignore[import-not-found]
                    AnswerRelevancyMetric,
                )
                from deepeval.metrics.faithfulness import (  # type: ignore[import-not-found]
                    FaithfulnessMetric,
                )
                from deepeval.test_case import LLMTestCase  # type: ignore[import-not-found]
            test_case = LLMTestCase(
                input=question,
                actual_output=answer,
                retrieval_context=contexts,
            )
            metrics: dict[str, float | None] = {}
            for cls, key in (
                (AnswerRelevancyMetric, "answer_relevancy"),
                (FaithfulnessMetric, "faithfulness"),
            ):
                try:
                    m = cls(threshold=0.5)
                    m.measure(test_case)
                    metrics[key] = float(getattr(m, "score", 0.0))
                except Exception as _e:  # noqa: BLE001
                    metrics[key] = None
                    metrics[f"{key}_error"] = str(_e)[:120]
            return {
                "available": True,
                "configured": True,
                "metrics": metrics,
                "input": {
                    "question": question[:80],
                    "answer_len": len(answer),
                    "context_count": len(contexts),
                },
            }
        except Exception as _exc:  # noqa: BLE001
            logger.warning("deepeval_evaluate_error: %s", _exc)
            return {
                "available": True,
                "configured": True,
                "error": str(_exc)[:200],
                "metrics": {
                    "answer_relevancy": None,
                    "faithfulness": None,
                },
            }


# ---------- Lakera + Rebuff ---------- (Stage-1 scaffold; prompt-injection defense)

class LakeraRebuffEngine:
    """Wraps Lakera Guard + Rebuff for prompt-injection defense.

    Per CLAUDE.md §40 (decision system), §47.6 (security: A11 prompt
    injection), §48 (AI explainability: guardrails_triggered audit row).

    Stage-1: import-safe stub (libs may not be installed; never raises).
    Stage-2: env-gated real invocation. Both Lakera and Rebuff offer
    API-based + self-hosted detection paths; the scaffold supports both.
        LAKERA_API_KEY    — opt-in Lakera Guard (https://lakera.ai)
        REBUFF_ENABLED=1  — enable Rebuff (self-hosted/SDK)

    fail-open: any detector error returns is_attack=False so a misconfigured
    detector never blocks a legitimate request. The audit row carries the
    error so ops can see + fix without losing traffic.
    """

    def __init__(self) -> None:
        self._lakera: Any = None
        self._rebuff: Any = None
        self._lakera_import_error: str | None = None
        self._rebuff_import_error: str | None = None
        try:
            import lakera_guard as lk  # type: ignore[import-not-found]
            self._lakera = lk
            logger.info("lakera_guard available")
        except Exception as exc:  # noqa: BLE001
            self._lakera_import_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.debug("lakera_guard unavailable; detector stubbed: %s", self._lakera_import_error)
        try:
            try:
                from documind_core.rebuff_detector import (  # type: ignore[import-not-found]
                    prepare_langchain_vectorstore_compat,
                )

                prepare_langchain_vectorstore_compat()
            except Exception as exc:  # noqa: BLE001
                logger.debug("rebuff compatibility shim unavailable: %s", exc)
            import rebuff as rb  # type: ignore[import-not-found]
            self._rebuff = rb
            logger.info("rebuff available")
        except Exception as exc:  # noqa: BLE001
            self._rebuff_import_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.debug("rebuff unavailable; detector stubbed: %s", self._rebuff_import_error)

    def is_available(self) -> bool:
        return self._lakera is not None or self._rebuff is not None

    def detect(self, *, prompt: str) -> dict[str, Any]:
        """Run prompt-injection detection across the configured detectors.

        Returns:
          {detector_name: {is_attack: bool, score: float|None, reason: str}}
          plus a top-level `is_attack` (any detector flagged).
        """
        import os as _os  # noqa: PLC0415
        out: dict[str, Any] = {"detectors": {}, "is_attack": False, "input_len": len(prompt)}
        rebuff_enabled = _os.getenv("REBUFF_ENABLED", "").strip() == "1"
        if not self.is_available() and not rebuff_enabled:
            out["available"] = False
            out["reason"] = "no detector library installed"
            out["stub"] = True
            return out
        # Lakera Guard (API)
        if self._lakera is not None and _os.getenv("LAKERA_API_KEY", "").strip():
            try:
                client = self._lakera.LakeraGuard(api_key=_os.environ["LAKERA_API_KEY"])
                result = client.detect(prompt)
                is_attack = bool(getattr(result, "flagged", False))
                out["detectors"]["lakera"] = {
                    "is_attack": is_attack,
                    "score": getattr(result, "score", None),
                    "categories": list(getattr(result, "categories", []) or [])[:5],
                }
                out["is_attack"] = out["is_attack"] or is_attack
            except Exception as _e:  # noqa: BLE001 — fail-open per §47
                out["detectors"]["lakera"] = {
                    "is_attack": False, "score": None, "error": str(_e)[:120],
                }
        # Rebuff: use the canonical runtime adapter so env handling,
        # thresholds, package drift, and fail-open behavior stay aligned
        # with inference.
        if rebuff_enabled:
            try:
                from documind_core.rebuff_detector import classify as _rebuff_classify  # type: ignore[import-not-found]
                from documind_core.rebuff_detector import status as _rebuff_status  # type: ignore[import-not-found]

                result = _rebuff_classify(prompt)
                out["detectors"]["rebuff"] = {
                    "is_attack": result.is_attack,
                    "score": result.score,
                    "raw_score": result.raw_score,
                    "available": result.available,
                    "error": result.error,
                    "layers": result.detection_layers,
                    "status": _rebuff_status(),
                }
                out["is_attack"] = out["is_attack"] or result.is_attack
            except Exception as _e:  # noqa: BLE001
                out["detectors"]["rebuff"] = {
                    "is_attack": False, "score": None, "error": str(_e)[:120],
                }
        out["available"] = True
        out["configured"] = bool(out["detectors"])
        return out


# ---------- Giskard ---------- (Stage-1 scaffold; LLM red-team + bias scan)

class GiskardEngine:
    """Wraps Giskard for LLM red-team + bias scanning.

    Per CLAUDE.md §40 (analysis: fairness/bias), §48.8 (fairness as part
    of explainability). Stage-1 stub; Stage-2 (env-gated) runs the
    Giskard scan suite when GISKARD_SCAN_ENABLED=1.
    """

    def __init__(self) -> None:
        self._giskard: Any = None
        self._import_error: str | None = None
        try:
            import giskard  # type: ignore[import-not-found]
            self._giskard = giskard
            logger.info("giskard %s available", getattr(giskard, "__version__", "?"))
        except Exception as exc:  # noqa: BLE001
            self._import_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.debug("giskard unavailable; scanner stubbed: %s", self._import_error)

    def is_available(self) -> bool:
        return self._giskard is not None

    def scan(self, *, model_callable: Any | None = None) -> dict[str, Any]:
        """Run Giskard's LLM scan. Stage-2: env-gated real invocation.

        model_callable: any callable(prompt: str) -> str. When None and
        GISKARD_SCAN_ENABLED is unset, returns stub. Per §47 fail-safe.
        """
        if not self.is_available():
            return {
                "available": False,
                "reason": self._import_error or "giskard not installed",
                "stub": True,
            }
        import os as _os  # noqa: PLC0415
        if _os.getenv("GISKARD_SCAN_ENABLED", "").strip() != "1":
            return {
                "available": True,
                "configured": False,
                "reason": "GISKARD_SCAN_ENABLED unset",
                "issues": [],
            }
        if model_callable is None:
            return {
                "available": True,
                "configured": True,
                "reason": "no model_callable provided",
                "issues": [],
            }
        try:
            # Giskard's LLM API surface is volatile across minor versions;
            # the scaffold isolates the exact call so version drift
            # only touches this block.
            gk = self._giskard
            # Use the high-level scan if available
            scan_fn = getattr(gk, "scan", None)
            if scan_fn is None:
                return {
                    "available": True,
                    "configured": True,
                    "error": "giskard.scan not in this version",
                    "issues": [],
                }
            report = scan_fn(model=model_callable)
            issues = []
            for attr in ("issues", "problems", "results"):
                if hasattr(report, attr):
                    issues = list(getattr(report, attr) or [])[:50]
                    break
            return {
                "available": True,
                "configured": True,
                "issues": [str(i)[:200] for i in issues],
                "issue_count": len(issues),
            }
        except Exception as _exc:  # noqa: BLE001
            logger.warning("giskard_scan_error: %s", _exc)
            return {
                "available": True,
                "configured": True,
                "error": str(_exc)[:200],
                "issues": [],
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
    lakera_rebuff = LakeraRebuffEngine()
    giskard = GiskardEngine()
    return {
        "stage": 2,
        "engines": {
            "ragas": {"available": ragas.is_available(), "import_error": ragas._import_error},
            "guardrails": {"available": guardrails.is_available()},
            "deepeval": {"available": deepeval.is_available(), "import_error": deepeval._import_error},
            "lakera_rebuff": {
                "available": lakera_rebuff.is_available(),
                "lakera_import_error": lakera_rebuff._lakera_import_error,
                "rebuff_import_error": lakera_rebuff._rebuff_import_error,
            },
            "giskard": {"available": giskard.is_available(), "import_error": giskard._import_error},
        },
        "all_available": (
            ragas.is_available()
            and guardrails.is_available()
            and deepeval.is_available()
            and lakera_rebuff.is_available()
            and giskard.is_available()
        ),
        "note": (
            "Stage-2 — eval engines wire real adapters behind env flags "
            "(RAGAS_EVAL_ENABLED, GUARDRAILS_EVAL_ENABLED, DEEPEVAL_ENABLED, "
            "LAKERA_API_KEY, REBUFF_ENABLED, GISKARD_SCAN_ENABLED). All paths "
            "fail-safe: import error → stub; flag unset → configured:false; "
            "adapter error → stub with error attached."
        ),
    }
