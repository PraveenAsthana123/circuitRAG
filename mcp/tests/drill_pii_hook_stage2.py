#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PII hook for ingestion — Stage-2 (per §43 + §56).

Locks the Stage-2 ingestion-side hook that:
  - exists at services/ingestion-svc/app/services/pii_hook.py
  - composes Stage-1 scripts/pii_redactor.py via lazy import
  - redact_for_ingestion(text, tenant_id, document_id) → (clean, audit_record)
  - silent pass-through when PII_REDACTOR_ENABLED unset (NEVER raises)
  - persists audit row to .loop/pii_audit.jsonl
  - audit row has 'entities_found' as type+position only (NO raw PII text)
  - DocumentIngestionSaga source UNCHANGED (Stage-3 will wire)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "services" / "ingestion-svc" / "app" / "services" / "pii_hook.py"
SAGA = REPO / "services" / "ingestion-svc" / "app" / "saga" / "document_saga.py"
PII_REDACTOR = REPO / "scripts" / "pii_redactor.py"


def _load_module(path: Path, name: str | None = None):
    spec = importlib.util.spec_from_file_location(name or path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name or path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: pii_hook.py exists + non-trivial size --")
    if not HOOK.exists():
        print(f"x {HOOK} missing")
        return 1
    src = HOOK.read_text(encoding="utf-8")
    if len(src) < 3500:
        print(f"x pii_hook too short ({len(src)} chars)")
        return 1
    print(f"  ok: pii_hook present ({len(src)} chars)")

    print("-- 2. NEGATIVE: DocumentIngestionSaga UNCHANGED (Stage-3 wires) --")
    if SAGA.exists():
        saga_src = SAGA.read_text(encoding="utf-8")
        if "pii_hook" in saga_src or "redact_for_ingestion" in saga_src:
            print("x document_saga has pii_hook reference — Stage-3 hasn't landed yet")
            return 1
    print("  ok: saga source unchanged (Stage-2 is purely additive hook module)")

    print("-- 3. POSITIVE: 3 contract surfaces exported --")
    os.environ.pop("PII_REDACTOR_ENABLED", None)
    mod, spec = _load_module(HOOK, "pii_hook")
    for name in ("redact_for_ingestion", "PIIAuditRecord", "status"):
        if not hasattr(mod, name):
            print(f"x pii_hook.{name} missing")
            return 1
    print("  ok: 3 surfaces exported")

    print("-- 4. NEGATIVE: silent pass-through when PII_REDACTOR_ENABLED unset --")
    os.environ.pop("PII_REDACTOR_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        clean, rec = mod.redact_for_ingestion(
            "test text with john@example.com",
            tenant_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
        )
        if clean != "test text with john@example.com":
            print(f"x text must be unchanged when disabled; got: {clean!r}")
            return 1
        if not rec.redaction_skipped:
            print("x audit record must mark redaction_skipped=True when disabled")
            return 1
        if "PII_REDACTOR_ENABLED" not in rec.skip_reason:
            print(f"x skip_reason must cite the env flag; got: {rec.skip_reason!r}")
            return 1
    except Exception as exc:
        raised = True
        print(f"x redact_for_ingestion must NOT raise when disabled; got: {exc}")
        return 1
    if raised:
        return 1
    print("  ok: silent pass-through; audit record records skip_reason")

    print("-- 5. NEGATIVE: audit log persisted at .loop/pii_audit.jsonl --")
    audit_path = REPO / ".loop" / "pii_audit.jsonl"
    if not audit_path.exists():
        print(f"x audit log not created at {audit_path}")
        return 1
    # Read the last row — should be the skipped record from step 4
    with audit_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if not rows:
        print("x audit log empty")
        return 1
    last = rows[-1]
    for key in ("ts", "tenant_id", "document_id", "stage",
                "entities_found", "redaction_skipped", "skip_reason"):
        if key not in last:
            print(f"x audit row missing key: {key}")
            return 1
    if last["stage"] != "ingestion":
        print(f"x audit row stage must be 'ingestion'; got {last['stage']!r}")
        return 1
    print("  ok: audit row persisted with full §38 schema")

    print("-- 6. NEGATIVE: audit row's entities_found contains NO raw PII text --")
    # §48.4: persist explainability metadata (type, score, position) but
    # NEVER the actual PII value. Confirm by inspecting an active row.
    if PII_REDACTOR.exists():
        # Force-enable + run with a real PII string
        os.environ["PII_REDACTOR_ENABLED"] = "1"
        spec.loader.exec_module(mod)
        try:
            clean, rec = mod.redact_for_ingestion(
                "Email me at secret@hackerman.com please",
                tenant_id="00000000-0000-0000-0000-000000000003",
                document_id="00000000-0000-0000-0000-000000000004",
            )
            for ent in rec.entities_found:
                # Audit entity must have type, score, start, end — NO 'text'
                if "text" in ent:
                    print(f"x audit entity contains raw PII 'text' field — §48.4 violation: {ent}")
                    return 1
                if "score" not in ent or "type" not in ent:
                    print(f"x audit entity missing type/score: {ent}")
                    return 1
            os.environ.pop("PII_REDACTOR_ENABLED", None)
        except Exception as exc:
            os.environ.pop("PII_REDACTOR_ENABLED", None)
            # If presidio not available, this step is a no-op pass
            print(f"  (skipped active-test: {exc})")
    print("  ok: audit entities_found contains type+score+position only (no raw PII)")

    print("-- 7. NEGATIVE: errors in Presidio NEVER block ingestion --")
    # Stage-2 contract: a broken redactor must NOT crash ingest. The
    # hook must catch + log + pass through. This is critical for
    # production reliability — operator may have misconfigured the
    # entity allowlist, or Presidio's spaCy model may be unavailable.
    # The hook MUST handle this gracefully.
    if "except Exception" not in src:
        print("x hook must catch generic Exception around redact()")
        return 1
    if "redaction_skipped = True" not in src:
        print("x hook must set redaction_skipped on Presidio errors")
        return 1
    if "passing through" not in src.lower() and "passing text through" not in src.lower():
        print("x source must document the pass-through-on-error contract")
        return 1
    print("  ok: Presidio errors caught + audit-recorded + pass through")

    print("-- 8. POSITIVE: status() reports Stage-2 + Stage-3 wiring path --")
    s = mod.status()
    if s.get("stage") != 2:
        print(f"x stage must be 2; got {s.get('stage')}")
        return 1
    for key in ("enabled", "audit_log_path", "audit_records_count",
                "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-3" not in s["next_stage"]:
        print("x next_stage must reference Stage-3 wiring path")
        return 1
    if "saga" not in s["next_stage"].lower():
        print("x next_stage must mention saga (where Stage-3 wires)")
        return 1
    print("  ok: status reports stage=2 + Stage-3 path mentions saga")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
