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
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

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
