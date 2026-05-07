#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: WhatsApp webhook gateway Stage-1 (per §43 + §56).

Locks the operator-supplied WhatsApp gateway shape:
  - Meta Cloud API + Twilio normalizers
  - HMAC signature verification (SHA-256 for Meta, SHA-1 for Twilio)
  - Outbound formatters per provider
  - Default-deny handler

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "whatsapp_webhook.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: whatsapp_webhook.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 5000:
        print(f"x whatsapp_webhook too short ({len(src)} chars)")
        return 1
    print(f"  ok: whatsapp_webhook present ({len(src)} chars)")

    print("-- 2. POSITIVE: 8+ contract surfaces exported --")
    os.environ["WHATSAPP_WEBHOOK_ENABLED"] = "1"
    mod, spec = _load_module(ADAPTER)
    expected = (
        "is_available", "status", "handle_inbound",
        "normalize_meta_webhook", "normalize_twilio_webhook",
        "verify_meta_signature", "verify_twilio_signature",
        "verify_meta_get_challenge",
        "format_outbound_meta", "format_outbound_twilio",
        "InboundMessage", "OutboundMessage",
        "WhatsAppWebhookDisabled",
    )
    for name in expected:
        if not hasattr(mod, name):
            print(f"x whatsapp_webhook.{name} missing")
            return 1
    print(f"  ok: {len(expected)} surfaces exported (Meta + Twilio + verify + format)")

    print("-- 3. NEGATIVE: default-deny — handle_inbound() raises when env unset --")
    os.environ.pop("WHATSAPP_WEBHOOK_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.handle_inbound({})
    except mod.WhatsAppWebhookDisabled as exc:
        raised = True
        if "WHATSAPP_WEBHOOK_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x handle_inbound() should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    # Re-enable
    os.environ["WHATSAPP_WEBHOOK_ENABLED"] = "1"
    spec.loader.exec_module(mod)

    print("-- 4. NEGATIVE: Meta normalizer parses + skips non-text events --")
    # Real-shape Meta Cloud API webhook (text message)
    meta_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"display_phone_number": "+15551234567"},
                    "messages": [{
                        "id": "wamid.ABC",
                        "from": "16509998888",
                        "timestamp": "1714862400",
                        "type": "text",
                        "text": {"body": "Hello"},
                    }],
                },
            }],
        }],
    }
    msg = mod.normalize_meta_webhook(meta_payload)
    if msg is None:
        print("x meta normalizer returned None for valid text payload")
        return 1
    if msg.from_number != "16509998888":
        print(f"x from_number wrong: {msg.from_number!r}")
        return 1
    if msg.text != "Hello":
        print(f"x text wrong: {msg.text!r}")
        return 1
    if msg.provider != "meta":
        print(f"x provider tag wrong: {msg.provider!r}")
        return 1
    # Status update (no messages key) → returns None
    status_payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "s1"}]}}]}]}
    if mod.normalize_meta_webhook(status_payload) is not None:
        print("x meta normalizer must return None on non-message events")
        return 1
    print("  ok: Meta normalizer parses text + skips non-text")

    print("-- 5. NEGATIVE: Twilio normalizer parses + handles whatsapp: prefix --")
    twilio_payload = {
        "From": "whatsapp:+16509998888",
        "To": "whatsapp:+15551234567",
        "Body": "Hi there",
        "MessageSid": "SM123",
    }
    msg = mod.normalize_twilio_webhook(twilio_payload)
    if msg is None:
        print("x twilio normalizer returned None for valid payload")
        return 1
    # Twilio prefix must be stripped
    if msg.from_number != "+16509998888":
        print(f"x whatsapp: prefix not stripped from from_number: {msg.from_number!r}")
        return 1
    if msg.text != "Hi there":
        print(f"x text wrong: {msg.text!r}")
        return 1
    if msg.provider != "twilio":
        print(f"x provider tag wrong: {msg.provider!r}")
        return 1
    # Missing fields → None
    if mod.normalize_twilio_webhook({}) is not None:
        print("x twilio normalizer must return None on missing From/To")
        return 1
    print("  ok: Twilio normalizer parses + strips whatsapp: prefix")

    print("-- 6. NEGATIVE: Meta HMAC-SHA256 signature verification works --")
    # Real Meta verification: HMAC-SHA256(body, app_secret) → hex
    import hashlib as _hashlib
    import hmac as _hmac
    body = b'{"test":"payload"}'
    secret = "myappsecret"
    valid_sig = "sha256=" + _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
    if not mod.verify_meta_signature(body, valid_sig, secret):
        print("x verify_meta_signature returned False on valid signature")
        return 1
    # Invalid signature
    if mod.verify_meta_signature(body, "sha256=deadbeef", secret):
        print("x verify_meta_signature returned True on invalid signature")
        return 1
    # Wrong scheme
    if mod.verify_meta_signature(body, "md5=abc", secret):
        print("x verify_meta_signature must reject non-sha256 schemes")
        return 1
    print("  ok: Meta HMAC-SHA256 verification — valid passes, invalid rejected")

    print("-- 7. NEGATIVE: Twilio HMAC-SHA1 + outbound formatters --")
    import base64 as _b64
    full_url = "https://example.com/webhooks/whatsapp"
    form = {"From": "whatsapp:+16509998888", "Body": "test"}
    auth = "twilioauth"
    sorted_params = sorted(form.items())
    canonical = full_url + "".join(f"{k}{v}" for k, v in sorted_params)
    digest = _hmac.new(auth.encode(), canonical.encode(), _hashlib.sha1).digest()
    valid_t_sig = _b64.b64encode(digest).decode("ascii")
    if not mod.verify_twilio_signature(full_url=full_url, form_params=form,
                                        signature=valid_t_sig, auth_token=auth):
        print("x verify_twilio_signature returned False on valid signature")
        return 1
    if mod.verify_twilio_signature(full_url=full_url, form_params=form,
                                    signature="bogus", auth_token=auth):
        print("x verify_twilio_signature returned True on invalid signature")
        return 1
    # Outbound format check
    outbound = mod.OutboundMessage(to_number="+16509998888", text="Hello back")
    meta_body = mod.format_outbound_meta(outbound)
    if meta_body.get("messaging_product") != "whatsapp":
        print("x meta outbound must include messaging_product=whatsapp")
        return 1
    if meta_body.get("to") != "+16509998888":
        print(f"x meta outbound 'to' wrong: {meta_body.get('to')!r}")
        return 1
    twilio_body = mod.format_outbound_twilio(outbound)
    if twilio_body.get("To") != "whatsapp:+16509998888":
        print(f"x twilio outbound must add whatsapp: prefix: {twilio_body.get('To')!r}")
        return 1
    print("  ok: Twilio HMAC-SHA1 + outbound formatters (Meta + Twilio)")

    print("-- 8. POSITIVE: status() reports stage=1 + Stage-2 wiring + provider list --")
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    if s.get("providers_supported") != ["meta", "twilio"]:
        print(f"x providers_supported must be ['meta', 'twilio']; got {s.get('providers_supported')}")
        return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "api-gateway" not in s["next_stage"] and "FastAPI" not in s["next_stage"]:
        print("x next_stage must mention FastAPI/api-gateway wiring site")
        return 1
    if "gemma_agent_council" not in s["next_stage"]:
        print("x next_stage must mention gemma_agent_council dispatch")
        return 1
    print("  ok: status reports stage=1 + Meta/Twilio + Stage-2 path")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
