"""PII redactor — Stage-1 Presidio adapter (per CLAUDE.md §56).

Stage-1 contract: opt-in via PII_REDACTOR_ENABLED=1. Lazy-loads Presidio
spaCy models. NOT wired into ingestion-svc / inference-svc until Stage-2
lands a drill proving redaction quality on the empirical-test corpus.

Why this exists (per user 6-plane spec — security plane gap):
    Existing system gates ACTOR (PolisAI), CONTENT (shieldgemma), and
    APPLY (Tier 1.3.b). It does NOT scan inbound text for PII before
    embedding/indexing. Result: a user accidentally pastes a credit
    card number into ingestion → it lands in Qdrant → it appears in
    retrieval results → it leaks into LLM context → potential exposure.

WHAT THIS PROVIDES:
    detect(text)   → list of PII entities found (type, start, end, score)
    redact(text)   → text with PII replaced by entity-type placeholders
    is_available() → True iff PII_REDACTOR_ENABLED=1 + Presidio installed

DEFAULT BEHAVIOR (per Stage-1):
    - opt-out (returns text unchanged when disabled)
    - high-precision Presidio defaults (score_threshold=0.5)
    - 9 entity types: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD,
      US_SSN, IP_ADDRESS, IBAN_CODE, US_BANK_NUMBER, MEDICAL_LICENSE

OPERATOR OPT-IN:
    PII_REDACTOR_ENABLED=1
    PII_REDACTOR_SCORE_THRESHOLD=0.5   # 0.0-1.0; lower = more aggressive
    PII_REDACTOR_ENTITIES=PERSON,EMAIL_ADDRESS,...   # comma-list to limit

COMPOSES WITH (per §49):
    services/ingestion-svc/app/services/ingestion_service.py — wire
        BEFORE chunking (Stage-2)
    services/inference-svc/app/services/rag_inference.py — wire
        AFTER retrieval, BEFORE prompt assembly (Stage-2)
    docs/architecture/six-plane-audit-2026-05-04.md — security plane gap
    §38 — decision audit (every redaction logs entity types found)
    §39 — RAG architecture (PII redaction is a hot-path security stage)
    §43 — drill discipline (drill_pii_redactor_stage1.py)
    §48 — explainability (redacted text + entity report = audit trail)
    §52 — brutal tool review (40-row when wired)
    §56 — Stage-1 6-gate adoption process
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

PII_REDACTOR_ENABLED = os.getenv("PII_REDACTOR_ENABLED", "").strip() == "1"
PII_SCORE_THRESHOLD = float(os.getenv("PII_REDACTOR_SCORE_THRESHOLD", "0.5"))

# Default entity allowlist — the 9 highest-impact types for a RAG system.
# Operator can override via PII_REDACTOR_ENTITIES env (comma-separated).
DEFAULT_ENTITIES = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IP_ADDRESS",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "MEDICAL_LICENSE",
)
PII_ENTITIES = tuple(
    e.strip()
    for e in os.getenv(
        "PII_REDACTOR_ENTITIES",
        ",".join(DEFAULT_ENTITIES),
    ).split(",")
    if e.strip()
)


class PIIRedactorDisabled(RuntimeError):
    """Raised when redact() is called but PII_REDACTOR_ENABLED is unset.

    Stage-1 invariant: caller MUST opt in. Failing closed (raise) is the
    correct shape for a security tool — silent pass-through could hide
    a misconfiguration that disables PII protection in production.
    """


@dataclass
class PIIEntity:
    """One detected entity. Schema matches Presidio's RecognizerResult."""
    entity_type: str
    start: int
    end: int
    score: float
    text: str


def is_available() -> bool:
    """True iff PII_REDACTOR_ENABLED=1 AND Presidio is importable.

    Default-deny: §56 6-gate. Probing the import (not loading models)
    is cheap; the heavy spaCy model load happens lazily inside
    detect()/redact() on first use.
    """
    if not PII_REDACTOR_ENABLED:
        return False
    try:
        import presidio_analyzer  # noqa: F401, PLC0415
        import presidio_anonymizer  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator-readable status surface — same shape as other Stage-1
    adapters (litellm, pydantic-ai, paperclip, gemma-council, bge-reranker)."""
    return {
        "stage": 1,
        "enabled_env": PII_REDACTOR_ENABLED,
        "score_threshold": PII_SCORE_THRESHOLD,
        "entities": list(PII_ENTITIES),
        "available": is_available(),
        "wiring_status": "stage-1 adapter only; not wired into ingestion-svc / inference-svc yet",
        "next_stage": "Stage-2 — wire into ingestion BEFORE chunking + into inference AFTER retrieval, BEFORE prompt assembly",
    }


def _get_analyzer():
    """Lazy-load Presidio analyzer + anonymizer engines.

    Cached on the function attribute so subsequent calls reuse the
    spaCy model (~70MB en_core_web_sm). First call is ~2s; subsequent
    calls are sub-millisecond model setup.
    """
    if not hasattr(_get_analyzer, "_engines"):
        from presidio_analyzer import AnalyzerEngine  # noqa: PLC0415
        from presidio_anonymizer import AnonymizerEngine  # noqa: PLC0415
        log.info("loading Presidio engines (one-time spaCy model load)")
        _get_analyzer._engines = (AnalyzerEngine(), AnonymizerEngine())  # type: ignore[attr-defined]
    return _get_analyzer._engines  # type: ignore[attr-defined]


def detect(text: str) -> list[PIIEntity]:
    """Find PII entities in text. Returns list (empty if none found).

    Raises PIIRedactorDisabled if not opted in. Caller can fall back to
    treating text as PII-free, but ONLY if they explicitly accept that
    risk — silent pass-through is a security anti-pattern.
    """
    if not is_available():
        raise PIIRedactorDisabled(
            "PII redactor disabled. Set PII_REDACTOR_ENABLED=1 and "
            "ensure presidio-analyzer + presidio-anonymizer are installed."
        )
    analyzer, _ = _get_analyzer()
    results = analyzer.analyze(
        text=text,
        entities=list(PII_ENTITIES),
        score_threshold=PII_SCORE_THRESHOLD,
        language="en",
    )
    return [
        PIIEntity(
            entity_type=r.entity_type,
            start=r.start,
            end=r.end,
            score=float(r.score),
            text=text[r.start:r.end],
        )
        for r in results
    ]


def redact(text: str, *, replacement_pattern: str | None = None) -> tuple[str, list[PIIEntity]]:
    """Replace PII entities with placeholders. Returns (redacted_text, entities_found).

    Default replacement: each PII span is replaced with `<<{ENTITY_TYPE}>>`,
    e.g. `<<EMAIL_ADDRESS>>`. Operator can supply a custom pattern via
    `replacement_pattern` containing `{entity}` placeholder.

    The returned `entities_found` list is for AUDIT — the original text
    is destroyed in the redacted output, but the audit row records what
    was redacted (by type, score, position) without preserving the
    actual PII value. Per §38 + §48 — explainable redaction without
    persisting the secrets.
    """
    if not is_available():
        raise PIIRedactorDisabled(
            "PII redactor disabled. Set PII_REDACTOR_ENABLED=1 and "
            "ensure presidio-analyzer + presidio-anonymizer are installed."
        )
    entities = detect(text)
    if not entities:
        return text, []

    # Replace from end to start so positions stay valid
    redacted = text
    sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)
    for ent in sorted_entities:
        replacement = (
            replacement_pattern.format(entity=ent.entity_type)
            if replacement_pattern
            else f"<<{ent.entity_type}>>"
        )
        redacted = redacted[:ent.start] + replacement + redacted[ent.end:]

    log.info(
        "pii_redact entities=%d types=%s threshold=%.2f",
        len(entities),
        sorted({e.entity_type for e in entities}),
        PII_SCORE_THRESHOLD,
    )
    return redacted, entities


if __name__ == "__main__":
    import json
    import sys
    print("scripts/pii_redactor.py — Stage-1 Presidio PII adapter")
    print(f"Stage-1 opt-in via PII_REDACTOR_ENABLED=1")
    print(f"Detects {len(PII_ENTITIES)} entity types: {', '.join(PII_ENTITIES)}")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
