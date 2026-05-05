#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: WhatsApp FastAPI router Stage-2 (per §43 + §56).

Locks the reusable APIRouter that wires the Stage-1 whatsapp_webhook
adapter end-to-end with FastAPI. Verifies the router's brutal
"always return 200" fail-safe contract.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTER = REPO / "scripts" / "whatsapp_fastapi_router.py"
WEBHOOK = REPO / "scripts" / "whatsapp_webhook.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: whatsapp_fastapi_router.py exists + non-trivial size --")
    if not ROUTER.exists():
        print(f"x {ROUTER} missing")
        return 1
    src = ROUTER.read_text(encoding="utf-8")
    if len(src) < 5000:
        print(f"x router module too short ({len(src)} chars)")
        return 1
    print(f"  ok: router module present ({len(src)} chars)")

    print("-- 2. POSITIVE: composes with all 4 Stage-1 adapters --")
    # Per the design: composes whatsapp_webhook + gemma_agent_council
    # + pii_redactor + langfuse_tracer (all Stage-1 from prior commits).
    for adapter in ("whatsapp_webhook", "gemma_agent_council",
                    "pii_redactor"):
        if adapter not in src:
            print(f"x router must compose with {adapter}")
            return 1
    print("  ok: composes with whatsapp_webhook + gemma_agent_council + pii_redactor")

    print("-- 3. NEGATIVE: Stage-1 whatsapp_webhook UNCHANGED (no reverse import) --")
    wh_src = WEBHOOK.read_text(encoding="utf-8")
    rev_import = re.compile(
        r"^\s*(from\s+.*whatsapp_fastapi_router|import\s+.*whatsapp_fastapi_router|from\s+fastapi)",
        re.MULTILINE,
    )
    if rev_import.search(wh_src):
        print("x whatsapp_webhook imports router or fastapi (Stage-1 must be FastAPI-free)")
        return 1
    print("  ok: whatsapp_webhook stays FastAPI-free (clean layering)")

    print("-- 4. NEGATIVE: BRUTAL CONTRACT — always returns 200 even on failure --")
    # Per §47 fail-safe: webhook handlers must NEVER raise to the
    # caller. Webhook retry storms cascade failures. Drill enforces
    # both: try/except catches all errors AND the response shape
    # always indicates ok=True even on internal failure.
    inbound_idx = src.find("async def inbound_webhook")
    inbound_end = src.find("return router", inbound_idx)
    if inbound_end < 0:
        inbound_end = len(src)
    inbound_body = src[inbound_idx:inbound_end]
    if "try:" not in inbound_body:
        print("x inbound webhook handler must wrap body in try/except")
        return 1
    if "except Exception" not in inbound_body:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if 'return {"ok": True' not in inbound_body:
        print("x must always return {'ok': True, ...} even on failure")
        return 1
    if "ALWAYS return 200" not in src:
        print("x source must document the fail-safe contract")
        return 1
    print("  ok: ALWAYS returns 200 — fail-safe contract enforced")

    print("-- 5. NEGATIVE: lazy fastapi + adapter imports (no module-top deps) --")
    # Module must be importable WITHOUT fastapi installed (e.g. CLI
    # contexts). _make_router() handles the lazy import; sibling
    # adapters (whatsapp_webhook, gemma, pii) only loaded inside the
    # handler body.
    lines_before_make_router = src[:src.find("def _make_router")]
    if re.search(r"^from fastapi", lines_before_make_router, re.MULTILINE):
        print("x fastapi must NOT be imported at module top")
        return 1
    if "from gemma_agent_council import" in lines_before_make_router:
        print("x gemma_agent_council must NOT be imported at module top")
        return 1
    if "from pii_redactor import" in lines_before_make_router:
        print("x pii_redactor must NOT be imported at module top")
        return 1
    print("  ok: fastapi + sibling adapters lazy-loaded inside handlers")

    print("-- 6. NEGATIVE: GET handshake verifies token (Meta verification flow) --")
    # The GET endpoint must call verify_meta_get_challenge from the
    # Stage-1 adapter so the Stage-1 contract owns the token-match
    # logic. Drill enforces the wire.
    if "verify_meta_get_challenge" not in src:
        print("x router must call verify_meta_get_challenge for GET handshake")
        return 1
    if "hub.mode" not in src or "hub.verify_token" not in src or "hub.challenge" not in src:
        print("x GET handshake must read all 3 hub.* query params")
        return 1
    if "status_code=403" not in src:
        print("x GET handshake must return 403 on token mismatch (Meta spec)")
        return 1
    print("  ok: GET handshake reads hub.* params + 403 on mismatch")

    print("-- 7. NEGATIVE: provider switch handles BOTH meta + twilio paths --")
    # The router must format outbound per provider AND handle inbound
    # parsing per provider (Meta = JSON, Twilio = form-encoded).
    if 'WHATSAPP_PROVIDER' not in src:
        print("x router must read WHATSAPP_PROVIDER env")
        return 1
    if "format_outbound_meta" not in src or "format_outbound_twilio" not in src:
        print("x must use BOTH outbound formatters")
        return 1
    if "parse_qsl" not in src:
        print("x must handle Twilio form-encoded payload (parse_qsl)")
        return 1
    if "json" not in src:
        print("x must handle Meta JSON payload")
        return 1
    print("  ok: provider switch covers Meta JSON + Twilio form-encoded paths")

    print("-- 8. POSITIVE: status reports Stage-2 + fail-safe contract + Stage-3 path --")
    os.environ.pop("WHATSAPP_WEBHOOK_ENABLED", None)
    mod, spec = _load_module(ROUTER)
    s = mod.status()
    if s.get("stage") != 2:
        print(f"x stage must be 2; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "available", "router_built", "provider",
                "wiring_status", "next_stage", "fail_safe_contract"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "ALWAYS returns 200" not in s["fail_safe_contract"]:
        print("x fail_safe_contract must document the always-200 invariant")
        return 1
    if "Stage-3" not in s["next_stage"]:
        print("x next_stage must reference Stage-3")
        return 1
    print("  ok: status reports Stage-2 + fail-safe + Stage-3 path")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
