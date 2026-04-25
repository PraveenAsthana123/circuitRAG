"""
Evaluation service (Design Areas 26, 59, 60, 61).

Exposes two endpoints:

* ``POST /api/v1/evaluation/run`` - run a dataset through retrieval +
  inference, compute metrics, return aggregate.
* ``POST /api/v1/evaluation/regression-gate`` - compare against a baseline.

This is the lightest of the four Python services. Full shape documented in
spec Areas 26 / 59 / 60 / 61.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from documind_core.config import BaseServiceSettings, get_settings
from documind_core.logging_config import setup_logging
from documind_core.middleware import (
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
    TenantContextMiddleware,
    register_exception_handlers,
)
from documind_core.observability import instrument_fastapi, setup_observability
from documind_core.schemas import HealthResponse
from fastapi import FastAPI
from pydantic import BaseModel

from app.metrics import MRR, NDCG, AnswerRelevance, Faithfulness, PrecisionAtK, Recall

log = logging.getLogger(__name__)


class EvaluationSettings(BaseServiceSettings):
    service_name: str = "evaluation-svc"


class ScoringDatapoint(BaseModel):
    question: str
    expected_chunk_ids: list[str]
    ground_truth_answer: str
    retrieved_chunk_ids: list[str]
    retrieved_context: str
    predicted_answer: str


class RunRequest(BaseModel):
    datapoints: list[ScoringDatapoint]
    precision_k: int = 5


class RunResponse(BaseModel):
    n: int
    precision_at_k: float
    recall: float
    mrr: float
    ndcg_at_10: float
    faithfulness: float
    answer_relevance: float


# ---- Regression gate schemas --------------------------------------
# Default tolerances are intentionally conservative — a 2% drop on any
# quality metric blocks rollout. Operators tune via the request body
# when a model upgrade is expected to trade one metric for another
# (e.g. "we accept -3% mrr for +5% answer_relevance").
_DEFAULT_TOLERANCE = 0.02


class RegressionGateTolerance(BaseModel):
    precision_at_k: float = _DEFAULT_TOLERANCE
    recall: float = _DEFAULT_TOLERANCE
    mrr: float = _DEFAULT_TOLERANCE
    ndcg_at_10: float = _DEFAULT_TOLERANCE
    faithfulness: float = _DEFAULT_TOLERANCE
    answer_relevance: float = _DEFAULT_TOLERANCE


class RegressionGateRequest(BaseModel):
    current: RunResponse
    baseline: RunResponse
    tolerance: RegressionGateTolerance = RegressionGateTolerance()


class MetricDelta(BaseModel):
    metric: str
    baseline: float
    current: float
    delta: float
    tolerance: float
    passed: bool


class RegressionGateResponse(BaseModel):
    passed: bool
    deltas: list[MetricDelta]
    failed_metrics: list[str]


def create_app() -> FastAPI:
    settings = get_settings(EvaluationSettings)
    setup_logging(
        service_name=settings.service_name,
        level=settings.log_level,
        json_format=settings.log_json,
    )
    setup_observability(
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        environment=settings.env,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("evaluation_service_ready")
        yield

    app = FastAPI(
        title="DocuMind - Evaluation Service", version="0.1.0", lifespan=lifespan
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    instrument_fastapi(app)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="evaluation-svc")

    @app.post("/api/v1/evaluation/run", response_model=RunResponse, tags=["scoring"])
    async def run_scoring(body: RunRequest) -> RunResponse:
        p_at_k = PrecisionAtK(k=body.precision_k)
        recall = Recall()
        mrr = MRR()
        ndcg = NDCG(k=10)
        faith = Faithfulness()
        rel = AnswerRelevance()

        n = len(body.datapoints)
        if n == 0:
            return RunResponse(
                n=0, precision_at_k=0, recall=0, mrr=0, ndcg_at_10=0,
                faithfulness=0, answer_relevance=0,
            )

        totals = {"p": 0.0, "r": 0.0, "mrr": 0.0, "ndcg": 0.0, "f": 0.0, "rel": 0.0}
        for dp in body.datapoints:
            relevant = set(dp.expected_chunk_ids)
            totals["p"] += p_at_k.compute(retrieved=dp.retrieved_chunk_ids, relevant=relevant)
            totals["r"] += recall.compute(retrieved=dp.retrieved_chunk_ids, relevant=relevant)
            totals["mrr"] += mrr.compute(retrieved=dp.retrieved_chunk_ids, relevant=relevant)
            totals["ndcg"] += ndcg.compute(retrieved=dp.retrieved_chunk_ids, relevant=relevant)
            totals["f"] += faith.compute(answer=dp.predicted_answer, context=dp.retrieved_context)
            totals["rel"] += rel.compute(question=dp.question, answer=dp.predicted_answer)

        return RunResponse(
            n=n,
            precision_at_k=totals["p"] / n,
            recall=totals["r"] / n,
            mrr=totals["mrr"] / n,
            ndcg_at_10=totals["ndcg"] / n,
            faithfulness=totals["f"] / n,
            answer_relevance=totals["rel"] / n,
        )

    @app.post(
        "/api/v1/evaluation/regression-gate",
        response_model=RegressionGateResponse,
        tags=["scoring"],
    )
    async def regression_gate(body: RegressionGateRequest) -> RegressionGateResponse:
        """
        Compare a current eval run against a baseline. Returns
        ``passed=True`` only when every quality metric is within
        tolerance of the baseline (current >= baseline - tolerance).

        This is the "block rollout if quality regressed" gate
        referenced in the original docstring. CI pipelines can POST
        this against the latest run + the last-known-good baseline
        and fail the build on any flagged regression.

        Implementation contract:
          * Per-metric delta = current - baseline.
          * Per-metric passed = (delta >= -tolerance). A small drop
            within tolerance is acceptable; a larger drop fails.
          * Overall passed = all per-metric passed.
          * ``failed_metrics`` lists the names of regressed metrics
            so an alert / Slack post can name them directly.

        Why this shape:
          * Baseline is supplied by the caller, not stored — the
            evaluation service stays stateless. A future commit can
            wire baselines into governance.eval_baselines or similar.
          * Tolerance per-metric (not global) matches the reality
            that a model upgrade may trade one metric for another;
            operators set the tradeoff envelope explicitly.
        """
        c = body.current
        b = body.baseline
        t = body.tolerance
        # Pair each metric name with (baseline_value, current_value, tolerance).
        pairs = [
            ("precision_at_k", b.precision_at_k, c.precision_at_k, t.precision_at_k),
            ("recall",         b.recall,         c.recall,         t.recall),
            ("mrr",            b.mrr,            c.mrr,            t.mrr),
            ("ndcg_at_10",     b.ndcg_at_10,     c.ndcg_at_10,     t.ndcg_at_10),
            ("faithfulness",   b.faithfulness,   c.faithfulness,   t.faithfulness),
            ("answer_relevance", b.answer_relevance, c.answer_relevance, t.answer_relevance),
        ]
        deltas: list[MetricDelta] = []
        failed: list[str] = []
        for name, base, cur, tol in pairs:
            delta = cur - base
            # Negative delta = regression. -0.005 with tolerance 0.02 passes;
            # -0.05 with tolerance 0.02 fails.
            metric_passed = delta >= -tol
            if not metric_passed:
                failed.append(name)
            deltas.append(MetricDelta(
                metric=name, baseline=base, current=cur,
                delta=delta, tolerance=tol, passed=metric_passed,
            ))
        return RegressionGateResponse(
            passed=(not failed),
            deltas=deltas,
            failed_metrics=failed,
        )

    return app


app = create_app()
