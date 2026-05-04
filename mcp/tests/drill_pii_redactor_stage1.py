#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PII redactor Stage-1 adapter (per §43 + §56 + §48).

Locks the Presidio Stage-1 adapter that:
  - exists as scripts/pii_redactor.py (separate module, not modifying ingestion)
  - 5 contract surfaces: is_available, detect, redact, status, PIIRedactorDisabled
  - Default opt-out (PII_REDACTOR_ENABLED unset → is_available()=False)
  - When disabled → detect/redact raises PIIRedactorDisabled (FAILS CLOSED)
  - Lazy Presidio import + lazy spaCy model load
  - Default 9-entity allowlist (PERSON, EMAIL_ADDRESS, ... MEDICAL_LICENSE)
  - Default score_threshold=0.5 (operator override via env)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PII = REPO / "scripts" / "pii_redactor.py"
INGEST = REPO / "services" / "ingestion-svc" / "app" / "services" / "ingestion_service.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: pii_redactor.py exists as a SEPARATE module --")
    if not PII.exists():
        print(f"x {PII} missing")
        return 1
    src = PII.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x pii_redactor module too short ({len(src)} chars)")
        return 1
    print(f"  ok: pii_redactor present ({len(src)} chars)")

    print("-- 2. NEGATIVE: ingestion_service.py UNCHANGED (no Stage-1 leakage) --")
    if INGEST.exists():
        ing_src = INGEST.read_text(encoding="utf-8")
        if "pii_redactor" in ing_src or "PIIRedactor" in ing_src:
            print("x ingestion_service has pii_redactor wiring — Stage-1 must NOT wire yet")
            return 1
    print("  ok: ingestion_service.py source unchanged (Stage-1 contract preserved)")

    print("-- 3. POSITIVE: 5 contract surfaces exported --")
    os.environ.pop("PII_REDACTOR_ENABLED", None)
    mod, spec = _load_module(PII)
    for name in ("is_available", "detect", "redact", "status", "PIIRedactorDisabled"):
        if not hasattr(mod, name):
            print(f"x pii_redactor.{name} missing")
            return 1
    print("  ok: 5 surfaces exported")

    print("-- 4. NEGATIVE: default is_available()=False (PII_REDACTOR_ENABLED unset) --")
    os.environ.pop("PII_REDACTOR_ENABLED", None)
    spec.loader.exec_module(mod)
    if mod.is_available():
        print(f"x default must be False; got {mod.is_available()}")
        return 1
    print("  ok: default opt-out preserved")

    print("-- 5. NEGATIVE: detect/redact FAIL CLOSED with PIIRedactorDisabled when off --")
    raised_d = False
    try:
        mod.detect("call me at 555-1234")
    except mod.PIIRedactorDisabled as exc:
        raised_d = True
        if "PII_REDACTOR_ENABLED" not in str(exc):
            print(f"x error msg must cite PII_REDACTOR_ENABLED; got: {exc}")
            return 1
    if not raised_d:
        print("x detect must raise when flag off (fail closed)")
        return 1
    raised_r = False
    try:
        mod.redact("call me at 555-1234")
    except mod.PIIRedactorDisabled:
        raised_r = True
    if not raised_r:
        print("x redact must raise when flag off")
        return 1
    print("  ok: both fail closed; cite PII_REDACTOR_ENABLED")

    print("-- 6. NEGATIVE: lazy Presidio import — NOT loaded at module top --")
    # The expensive thing is the spaCy model load inside _get_analyzer().
    # Top-level imports should be limited to typing / dataclasses / log.
    # presidio_analyzer + presidio_anonymizer must NOT be imported at
    # module top — only inside is_available() (cheap probe) and
    # _get_analyzer() (heavy load).
    lines_before_get = src[:src.find("def _get_analyzer")]
    if re.search(r"^from presidio_", lines_before_get, re.MULTILINE):
        print("x presidio modules must NOT be 'from'-imported at module top")
        return 1
    if re.search(r"^import presidio_", lines_before_get, re.MULTILINE):
        print("x presidio modules must NOT be imported at module top")
        return 1
    print("  ok: presidio lazy-loaded inside _get_analyzer / is_available")

    print("-- 7. NEGATIVE: 9 default entities + score_threshold default 0.5 --")
    s = mod.status()
    if len(s["entities"]) < 9:
        print(f"x default entity allowlist too short: {s['entities']}")
        return 1
    must_include = {"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
                    "US_SSN", "IP_ADDRESS", "MEDICAL_LICENSE"}
    missing = must_include - set(s["entities"])
    if missing:
        print(f"x default entity allowlist missing: {missing}")
        return 1
    if abs(s["score_threshold"] - 0.5) > 0.001:
        print(f"x default score_threshold must be 0.5; got {s['score_threshold']}")
        return 1
    print(f"  ok: {len(s['entities'])} default entities + threshold=0.5")

    print("-- 8. POSITIVE: status() reports Stage-1 + Stage-2 wiring path --")
    if s.get("stage") != 1:
        print(f"x status.stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "available", "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2 wiring path")
        return 1
    if "ingestion" not in s["next_stage"].lower():
        print("x next_stage must mention ingestion wiring (data-in path)")
        return 1
    if "inference" not in s["next_stage"].lower():
        print("x next_stage must mention inference wiring (data-out path)")
        return 1
    print("  ok: status reports stage=1 + Stage-2 wiring path (ingest + inference)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
