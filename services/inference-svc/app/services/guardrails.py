"""
Output guardrails (Design Area 33 — Output Contract, §38 AI Governance).

Runs before returning an LLM response to the user. Guardrails are
*defensive* — they don't fix bad output, they detect and route it. Detected
issues fan out to the governance-svc HITL queue for human review.

Checks:

1. **Empty answer** — zero-length or only whitespace.
2. **Citation present** — every answer must have at least one
   ``[Source: ...]`` tag.
3. **Citation validity** — cited labels must resolve to chunks we provided.
4. **PII pattern match** — coarse regex for emails, phone numbers, SSNs.
5. **Confidence score** — derived from citation coverage + retrieval scores.

Each failure is logged and attached to the response for the governance-svc
to act on.

Observability: every check() call is wrapped in an OTel span
``inference.guardrail.check`` with attributes for passed-state,
confidence, and violation counts. A matching ``guardrail_check_completed``
log line carries the same shape so operators can pivot between
Jaeger and logs without losing context. Closes one row of the
OTel tool-level coverage scorecard
(docs/architecture/otel-tool-level-coverage-scorecard-and-tracker.md):
inference-svc — "tool-decision and answer-quality spans".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

# OTel is optional on this code path — the same observability layer as
# server_common imports it tolerantly so libraries can run without the
# SDK installed (e.g. in unit tests). When present, tracer.start_as_
# current_span returns a real span; when absent we get a context that
# accepts set_attribute() as a no-op.
try:
    from opentelemetry import trace as _otel_trace
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False

log = logging.getLogger(__name__)
_tracer = _otel_trace.get_tracer(__name__) if _OTEL_AVAILABLE else None

# Coarse PII patterns — real prod wires a proper detector (AWS Comprehend,
# Presidio, on-device NER). These catch the common stuff.
_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "ssn"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "phone"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "email"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "credit_card_like"),
]


@dataclass
class GuardrailResult:
    passed: bool
    confidence: float
    violations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class GuardrailChecker:
    def __init__(
        self,
        *,
        min_answer_length: int = 10,
        require_citation: bool = True,
    ) -> None:
        self._min_len = min_answer_length
        self._require_citation = require_citation

    def check(
        self,
        *,
        answer: str,
        citation_map: list[dict[str, Any]],
        retrieval_scores: list[float],
    ) -> GuardrailResult:
        # Wrap the whole check in a span so Jaeger queries can filter
        # by guardrail.passed / guardrail.violations.count without
        # parsing logs. Falls through cleanly when OTel SDK isn't
        # installed (_NoopSpan-style — set_attribute is a no-op).
        if _tracer is not None:
            span_cm = _tracer.start_as_current_span("inference.guardrail.check")
        else:
            span_cm = _NoopSpan()
        with span_cm as sp:
            result = self._check_inner(
                answer=answer,
                citation_map=citation_map,
                retrieval_scores=retrieval_scores,
            )
            # Set span attributes from the result. ``set_attribute``
            # is safe on real spans + the noop placeholder.
            if sp is not None:
                sp.set_attribute("guardrail.passed", result.passed)
                sp.set_attribute("guardrail.confidence", result.confidence)
                sp.set_attribute(
                    "guardrail.violations.count", len(result.violations),
                )
                if result.violations:
                    # Comma-joined string keeps cardinality bounded
                    # (don't want one attribute per violation kind
                    # exploding the span-attribute count). Operators
                    # filter-contains on this in Jaeger.
                    sp.set_attribute(
                        "guardrail.violations",
                        ",".join(result.violations[:10]),
                    )
                # Surface the two sub-signals so a single Jaeger row
                # shows answer-quality posture without expansion.
                sp.set_attribute(
                    "guardrail.found_labels",
                    int(result.details.get("found_labels", 0)),
                )
                sp.set_attribute(
                    "guardrail.top_retrieval_score",
                    float(result.details.get("top_retrieval_score", 0.0)),
                )
            # Structured log line — same data as the span attributes
            # so operators pivot between Jaeger and log greps without
            # losing context. Drilled below.
            log.info(
                "guardrail_check_completed passed=%s confidence=%.3f "
                "violations=%s found_labels=%d top_score=%.3f",
                result.passed,
                result.confidence,
                ",".join(result.violations) if result.violations else "-",
                int(result.details.get("found_labels", 0)),
                float(result.details.get("top_retrieval_score", 0.0)),
            )
            return result

    def _check_inner(
        self,
        *,
        answer: str,
        citation_map: list[dict[str, Any]],
        retrieval_scores: list[float],
    ) -> GuardrailResult:
        """Original body of check(). Split out so the public surface
        wraps it in OTel + structured logging without cluttering
        the core logic."""
        violations: list[str] = []

        # 1. Empty answer
        if len(answer.strip()) < self._min_len:
            violations.append("empty_answer")

        # 2/3. Citation checks
        label_pattern = re.compile(r"\[Source:\s*([^,\]]+),\s*Page\s*(\d+)\]", re.IGNORECASE)
        found_labels = label_pattern.findall(answer)
        if self._require_citation and not found_labels:
            violations.append("no_citation")

        # Cross-check against the chunks we actually served — detects
        # hallucinated citations.
        served_labels = {c["label"] for c in citation_map}
        for filename, page in found_labels:
            label = f"[Source: {filename.strip()}, Page {page}]"
            if label not in served_labels:
                violations.append(f"hallucinated_citation:{label}")
                break  # one's enough — don't spam the log

        # 4. PII scan
        for pat, name in _PII_PATTERNS:
            if pat.search(answer):
                violations.append(f"pii_detected:{name}")

        # 5. Confidence score — simple heuristic
        # High = citations resolve AND top retrieval score is strong
        top_score = max(retrieval_scores, default=0.0)
        cite_coverage = 1.0 if found_labels else 0.0
        confidence = round(0.4 * cite_coverage + 0.6 * min(top_score, 1.0), 3)

        passed = not violations
        if not passed:
            log.warning("guardrail_failed violations=%s", violations)

        return GuardrailResult(
            passed=passed,
            confidence=confidence,
            violations=violations,
            details={"found_labels": len(found_labels), "top_retrieval_score": top_score},
        )


class _NoopSpan:
    """Stand-in for an OTel span when the SDK isn't installed.
    Acts as a context manager that yields itself; set_attribute is
    a no-op. Avoids ``if sp is not None`` chains everywhere."""

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        pass
