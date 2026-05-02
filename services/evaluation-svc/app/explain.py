"""
§48 Explainability endpoint — `/api/v1/explain?prediction_id=<id>`.

Implements the §48.4 decision audit row contract: every regulated AI
decision is persisted as a row keyed on `prediction_id`, retrievable
via this endpoint to satisfy EU AI Act Art. 86 (right to explanation)
and NIST AI RMF logging.

This is the V1 stub — store is in-process, not durable. A future
iteration migrates to Postgres `governance.decision_audit` so the row
survives service restart and becomes queryable across instances. The
schema is the durable contract; the storage layer is incidental.

Endpoints:

  GET  /api/v1/explain?prediction_id=<id>   →  ExplainResponse | 404
  POST /api/v1/decisions                    →  DecisionAuditRow (201)

Why POST /decisions lives here:
  Without a way to seed the store, the GET endpoint can't be drilled
  end-to-end. POST is the same shape an inference-time hook would use
  to push a row when a prediction fires. In production this becomes a
  Kafka consumer, not an HTTP endpoint.

Privacy:
  PII fields (input_features) are redacted before storage if §38
  audit-redaction policy applies. The stub trusts the caller; the real
  implementation walks AI Governance ADR-013.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from documind_core.exceptions import NotFoundError, ValidationError
from fastapi import APIRouter, FastAPI, Query, status
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ---- Schemas (§48.4 row shape) ------------------------------------


class FeatureContribution(BaseModel):
    """Per-feature attribution (SHAP value, LIME weight, etc.)."""

    name: str
    value: Any
    contribution: float = Field(
        description=(
            "Signed contribution to the prediction. Positive pushes "
            "toward the predicted class; negative pulls away."
        ),
    )


class ExplanationDetail(BaseModel):
    """The four §48 explainability surfaces that may be present."""

    method: str = Field(
        description="shap | lime | counterfactual | rag_citations | tool_trace",
    )
    top_features: list[FeatureContribution] = Field(default_factory=list)
    counterfactual: str | None = Field(
        default=None,
        description=(
            "Human-readable counterfactual per EU AI Act Art. 86: "
            "the smallest plausible flip that would have changed the "
            "decision. Only changeable features (income, debt) — "
            "never age/gender/race."
        ),
    )
    citations: list[str] = Field(
        default_factory=list,
        description="For RAG decisions: source chunk IDs the answer cites.",
    )


class DecisionAuditRow(BaseModel):
    """§48.4 — every regulated AI decision persists this shape."""

    request_id: str
    prediction_id: str
    timestamp: datetime
    tenant_id: str
    user_id: str | None = None
    model_name: str
    model_version: str
    prompt_version: str | None = None
    input_features: dict[str, Any] | None = None
    input_hash: str | None = None
    prediction: Any
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: ExplanationDetail
    rules_applied: list[str] = Field(default_factory=list)
    guardrails_triggered: list[str] = Field(default_factory=list)
    human_override: bool = False
    fairness_flag: str = Field(
        default="pass",
        description="pass | warn | fail — fairness pre-deploy gate result",
    )
    latency_ms: int = Field(ge=0)
    cost_tokens: int | None = None
    feedback: str | None = None


class ExplainResponse(BaseModel):
    """What `/api/v1/explain` returns. The audit row is included
    verbatim so the response is self-describing — a regulator can
    extract the raw decision details and the explanation from the
    same payload."""

    audit: DecisionAuditRow
    explanation_method: str
    confidence: float
    counterfactual: str | None
    fairness_status: str


# ---- Store (in-process, ring-buffered) ----------------------------


class DecisionAuditStore:
    """Thread-safe ring-buffered LRU. Caps at ``capacity`` rows so a
    long-running stub doesn't OOM. In production this is replaced by
    Postgres governance.decision_audit per the §48 retention policy
    (7y for regulated, 1y hot for unregulated)."""

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = capacity
        self._rows: OrderedDict[str, DecisionAuditRow] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, row: DecisionAuditRow) -> None:
        with self._lock:
            self._rows[row.prediction_id] = row
            self._rows.move_to_end(row.prediction_id)
            while len(self._rows) > self._capacity:
                self._rows.popitem(last=False)

    def get(self, prediction_id: str) -> DecisionAuditRow | None:
        with self._lock:
            return self._rows.get(prediction_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._rows)


# ---- Router -------------------------------------------------------


def build_router(store: DecisionAuditStore) -> APIRouter:
    router = APIRouter(tags=["explainability"])

    @router.post(
        "/api/v1/decisions",
        response_model=DecisionAuditRow,
        status_code=status.HTTP_201_CREATED,
        summary="Seed a decision audit row (typically from a Kafka consumer)",
    )
    async def post_decision(row: DecisionAuditRow) -> DecisionAuditRow:
        if not row.prediction_id:
            raise ValidationError(
                "prediction_id is required",
                error_code="MISSING_PREDICTION_ID",
            )
        if not row.timestamp.tzinfo:
            # Force UTC so cross-tenant queries don't drift on TZ.
            row = row.model_copy(update={"timestamp": row.timestamp.replace(tzinfo=UTC)})
        store.put(row)
        log.info(
            "decision_audit_recorded prediction_id=%s model=%s@%s",
            row.prediction_id,
            row.model_name,
            row.model_version,
        )
        return row

    @router.get(
        "/api/v1/explain",
        response_model=ExplainResponse,
        summary="EU AI Act Art. 86 explanation for a past decision",
    )
    async def get_explain(
        prediction_id: str = Query(
            ...,
            min_length=1,
            description="The prediction_id from the original decision.",
        ),
    ) -> ExplainResponse:
        row = store.get(prediction_id)
        if row is None:
            raise NotFoundError(
                f"No decision audit row for prediction_id={prediction_id}",
                error_code="DECISION_NOT_FOUND",
            )
        return ExplainResponse(
            audit=row,
            explanation_method=row.explanation.method,
            confidence=row.confidence,
            counterfactual=row.explanation.counterfactual,
            fairness_status=row.fairness_flag,
        )

    return router


def register_explain(app: FastAPI) -> DecisionAuditStore:
    """Mount the explain endpoints on a FastAPI app and return the
    store so callers (drills, tests) can introspect or pre-seed."""
    store = DecisionAuditStore()
    app.state.explain_store = store
    app.include_router(build_router(store))
    return store
