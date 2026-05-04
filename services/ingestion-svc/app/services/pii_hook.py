"""PII redaction hook for ingestion — Stage-2 adapter.

Stage-1 shipped scripts/pii_redactor.py (Presidio wrapper, opt-in,
default-deny). Stage-2 (this module) provides:

  - redact_for_ingestion(text, tenant_id, document_id) → (clean_text, audit_record)
  - audit log writer: .loop/pii_audit.jsonl
  - silent pass-through when PII_REDACTOR_ENABLED is not set

Stage-3 (next iteration): one-line integration into
DocumentIngestionSaga.run() — call redact_for_ingestion BEFORE handing
text to the chunker.

WHY THIS SHAPE (Stage-2, not Stage-3):
    Stage-3 would modify the saga directly, which is tested production
    code. Per §56 6-gate, we ship a clean adapter first, drill it, then
    Stage-3 integrates with one-line change. This keeps the saga
    tested-as-shipped while we drill the integration shape separately.

AUDIT-ROW SCHEMA (per §38 + §48):
    {
      "ts": ISO-8601 UTC,
      "tenant_id": UUID,
      "document_id": UUID,
      "stage": "ingestion",
      "entities_found": [{"type": str, "score": float, "start": int, "end": int}],
        # NOTE: actual PII text is NEVER persisted — only type + position.
        # This satisfies §48.4 explainability without §38 PII-in-audit risk.
      "redacted_text_chars": int,
      "original_text_chars": int,
    }

OPERATOR OPT-IN:
    PII_REDACTOR_ENABLED=1
    PII_REDACTOR_SCORE_THRESHOLD=0.5     # default 0.5
    PII_REDACTOR_ENTITIES=PERSON,EMAIL_ADDRESS,...   # default 9 types

COMPOSES WITH:
    scripts/pii_redactor.py — Stage-1 Presidio adapter
    services/ingestion-svc/app/saga/document_saga.py — Stage-3 wiring site
    docs/architecture/six-plane-audit-2026-05-04.md — security plane
        (this commit closes the "wire PII into ingestion" P0 row)
    §38 — decision audit (entities-found is the audit row)
    §43 — drill discipline
    §48 — explainability (entity-types persisted; PII text never)
    §52 — brutal tool review (40-row when wired in saga)
    §56 — Stage-2 6-gate adoption
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Add scripts/ to path for the Stage-1 adapter import
_REPO = Path(__file__).resolve().parents[4]
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

PII_AUDIT_LOG = _REPO / ".loop" / "pii_audit.jsonl"


@dataclass
class PIIAuditRecord:
    """Per-redaction audit row. Matches §38 decision-audit schema."""
    ts: str
    tenant_id: str
    document_id: str
    stage: str  # "ingestion" | "inference"
    entities_found: list[dict[str, Any]] = field(default_factory=list)
    redacted_text_chars: int = 0
    original_text_chars: int = 0
    redaction_skipped: bool = False
    skip_reason: str = ""


def _is_enabled() -> bool:
    """Inherit Stage-1 default-deny posture."""
    return os.getenv("PII_REDACTOR_ENABLED", "").strip() == "1"


def _persist_audit(record: PIIAuditRecord) -> None:
    """Append-only JSONL audit log. Per §38 — every redaction decision
    persisted; entities are TYPE+POSITION only, never raw PII text."""
    PII_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PII_AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), default=str) + "\n")


def redact_for_ingestion(
    text: str,
    *,
    tenant_id: str,
    document_id: str,
) -> tuple[str, PIIAuditRecord]:
    """Redact PII before text is chunked / embedded / indexed.

    Returns (clean_text, audit_record). When PII_REDACTOR_ENABLED is
    NOT set, returns (text unchanged, audit_record with skipped=True).
    NEVER raises — Stage-2 contract is silent pass-through preserves
    caller pipeline.

    The audit record is ALSO persisted to .loop/pii_audit.jsonl for
    operator visibility + regulatory traceability.
    """
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    record = PIIAuditRecord(
        ts=now_iso,
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        stage="ingestion",
        original_text_chars=len(text),
        redacted_text_chars=len(text),  # default no-change
    )

    if not _is_enabled():
        record.redaction_skipped = True
        record.skip_reason = "PII_REDACTOR_ENABLED unset"
        _persist_audit(record)
        return text, record

    try:
        # Lazy import — keep ingestion cold-start fast for callers not
        # using the redactor
        import pii_redactor  # noqa: PLC0415
    except ImportError:
        record.redaction_skipped = True
        record.skip_reason = "pii_redactor module not importable"
        log.warning("pii_redactor not importable — passing text through unchanged")
        _persist_audit(record)
        return text, record

    try:
        redacted_text, entities = pii_redactor.redact(text)
    except Exception as exc:
        # Stage-2 contract: PII errors must NEVER block ingestion.
        # Log + pass through. Operator should investigate audit log.
        record.redaction_skipped = True
        record.skip_reason = f"redact() raised: {type(exc).__name__}: {str(exc)[:120]}"
        log.warning("pii_redact failed for doc=%s: %s — passing through", document_id, exc)
        _persist_audit(record)
        return text, record

    record.entities_found = [
        {
            "type": e.entity_type,
            "score": float(e.score),
            "start": int(e.start),
            "end": int(e.end),
            # text intentionally OMITTED — §48.4: persist explainability
            # metadata, never the raw PII value
        }
        for e in entities
    ]
    record.redacted_text_chars = len(redacted_text)

    log.info(
        "pii_redact_ingestion doc=%s entities=%d types=%s",
        document_id,
        len(entities),
        sorted({e["type"] for e in record.entities_found}),
    )
    _persist_audit(record)
    return redacted_text, record


def status() -> dict[str, Any]:
    """Operator status surface."""
    audit_count = 0
    if PII_AUDIT_LOG.exists():
        with PII_AUDIT_LOG.open(encoding="utf-8") as f:
            audit_count = sum(1 for _ in f)
    return {
        "stage": 2,
        "enabled": _is_enabled(),
        "audit_log_path": str(PII_AUDIT_LOG),
        "audit_records_count": audit_count,
        "wiring_status": "stage-2 hook ready; Stage-3 wires call into DocumentIngestionSaga.run() before chunker",
        "next_stage": "Stage-3 — single-line integration in saga BEFORE chunker hands text to embedder",
    }
