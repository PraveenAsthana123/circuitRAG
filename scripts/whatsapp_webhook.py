"""WhatsApp webhook gateway — Stage-1 adapter (per CLAUDE.md §56).

Realizes operator-supplied "MCP + WhatsApp" architecture spec.
Stage-1 ships the receiver + validator + payload normalizer.
Stage-2 wires into FastAPI route + agent-council dispatch.

ARCHITECTURE (per operator spec):
  WhatsApp User → WhatsApp Cloud (Meta or Twilio) → POST webhook
                                                  ↓
                         API Gateway (validates token/tenant)
                                                  ↓
                         WhatsApp Webhook (this module)
                                                  ↓
                         Security + PII pre-check
                                                  ↓
                         Gemma Agent Council (5-agent)
                                                  ↓
                         Response → WhatsApp Cloud → User

WHY THIS SHAPE (lightweight Stage-1):
  Twilio's WhatsApp Business API + Meta's WhatsApp Cloud API have
  different webhook payload shapes but same request flow. This
  adapter normalizes both into a single InboundMessage dataclass
  the agent council can consume. No external SDK required for
  Stage-1 — pure HMAC + payload parsing.

CONTRACT:
  - normalize_meta_webhook(payload) → InboundMessage
  - normalize_twilio_webhook(payload) → InboundMessage
  - verify_meta_signature(body, signature, secret) → bool
  - verify_twilio_signature(url, body, signature, auth_token) → bool
  - format_outbound_meta(message) → dict (ready to POST to Graph API)
  - format_outbound_twilio(message) → dict (ready to POST to Twilio)

OPERATOR OPT-IN:
    WHATSAPP_WEBHOOK_ENABLED=1
    WHATSAPP_PROVIDER=meta              # or "twilio"
    WHATSAPP_META_APP_SECRET=...        # for HMAC verification
    WHATSAPP_TWILIO_AUTH_TOKEN=...      # for Twilio sig verification
    WHATSAPP_VERIFY_TOKEN=...           # GET-verification token (Meta)

COMPOSES WITH (per §49):
    scripts/gemma_agent_council.py — Stage-2 dispatches inbound to
        run_council; outbound from council.final_output
    scripts/pii_redactor.py — Stage-2 scans inbound BEFORE council
    services/api-gateway — Stage-2 mounts the webhook route
    docs/architecture/six-plane-audit-2026-05-04.md — control plane
    §38 — decision audit (every webhook → audit row)
    §43 — drill discipline
    §52 — brutal tool review (40-row when wired into FastAPI)
    §56 — Stage-1 6-gate
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

WHATSAPP_WEBHOOK_ENABLED = os.getenv("WHATSAPP_WEBHOOK_ENABLED", "").strip() == "1"
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "meta").lower()
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")


class WhatsAppWebhookDisabled(RuntimeError):
    """Raised when webhook handler invoked but env flag unset."""


@dataclass
class InboundMessage:
    """Normalized inbound message — provider-agnostic.

    Both Meta Cloud API and Twilio Business API webhooks normalize
    to this shape. Downstream agent council sees a single contract.
    """
    provider: str          # "meta" | "twilio"
    message_id: str        # provider-assigned id (idempotency key)
    from_number: str       # E.164 sender phone
    to_number: str         # the WhatsApp Business phone the user wrote to
    text: str              # message body (text only — Stage-1)
    timestamp_unix: int    # provider timestamp (epoch seconds)
    raw: dict[str, Any] = field(default_factory=dict)  # full payload for audit


@dataclass
class OutboundMessage:
    """Normalized outbound message — agent council generates this."""
    to_number: str         # E.164 recipient
    text: str              # response body
    reply_to_message_id: str | None = None  # for threading


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return WHATSAPP_WEBHOOK_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": 1,
        "enabled_env": WHATSAPP_WEBHOOK_ENABLED,
        "available": is_available(),
        "provider": WHATSAPP_PROVIDER,
        "providers_supported": ["meta", "twilio"],
        "has_verify_token": bool(WHATSAPP_VERIFY_TOKEN),
        "has_meta_secret": bool(os.getenv("WHATSAPP_META_APP_SECRET")),
        "has_twilio_token": bool(os.getenv("WHATSAPP_TWILIO_AUTH_TOKEN")),
        "wiring_status": "stage-1 receiver + validator + normalizer; Stage-2 mounts FastAPI route + dispatches to gemma_agent_council",
        "next_stage": (
            "Stage-2 — services/api-gateway adds POST /webhooks/whatsapp "
            "+ GET /webhooks/whatsapp (verify_token); receiver normalizes "
            "via this adapter; PII pre-check then dispatches to "
            "scripts/gemma_agent_council.run_council; outbound formatted "
            "via format_outbound_* and POSTed to Cloud API"
        ),
    }


# ─── Inbound normalizers ─────────────────────────────────────────


def normalize_meta_webhook(payload: dict[str, Any]) -> InboundMessage | None:
    """Parse Meta Cloud API webhook payload into InboundMessage.

    Returns None for non-message events (status updates, deliveries).
    Per Meta API docs, the payload shape is:
      entry[0].changes[0].value.messages[0]

    Stage-1 supports text messages only. Media (image/audio/etc) is
    Stage-2.
    """
    try:
        entries = payload.get("entry", [])
        if not entries:
            return None
        changes = entries[0].get("changes", [])
        if not changes:
            return None
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None  # likely status update, not a message
        msg = messages[0]
        if msg.get("type") != "text":
            return None  # Stage-1 = text only
        metadata = value.get("metadata", {})
        return InboundMessage(
            provider="meta",
            message_id=msg.get("id", ""),
            from_number=msg.get("from", ""),
            to_number=metadata.get("display_phone_number", ""),
            text=(msg.get("text") or {}).get("body", ""),
            timestamp_unix=int(msg.get("timestamp", 0) or 0),
            raw=payload,
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("normalize_meta_webhook parse error: %s", exc)
        return None


def normalize_twilio_webhook(payload: dict[str, Any]) -> InboundMessage | None:
    """Parse Twilio WhatsApp webhook (form-encoded) into InboundMessage.

    Twilio uses form-encoded fields; caller passes the parsed form as
    a dict. Field names: From, To, Body, MessageSid.
    """
    try:
        from_raw = payload.get("From", "")
        to_raw = payload.get("To", "")
        if not from_raw or not to_raw:
            return None
        # Twilio prefixes WhatsApp numbers with "whatsapp:"
        from_number = from_raw.replace("whatsapp:", "")
        to_number = to_raw.replace("whatsapp:", "")
        return InboundMessage(
            provider="twilio",
            message_id=payload.get("MessageSid", ""),
            from_number=from_number,
            to_number=to_number,
            text=payload.get("Body", ""),
            timestamp_unix=0,  # Twilio doesn't include this in webhook
            raw=payload,
        )
    except (KeyError, TypeError) as exc:
        log.warning("normalize_twilio_webhook parse error: %s", exc)
        return None


# ─── Signature verification ──────────────────────────────────────


def verify_meta_signature(body: bytes, signature: str, app_secret: str) -> bool:
    """HMAC-SHA256 verification per Meta's X-Hub-Signature-256 header.

    Header format: 'sha256=<hex_digest>'
    Returns True only when computed HMAC matches.
    """
    if not signature.startswith("sha256="):
        return False
    expected_hex = signature.split("=", 1)[1]
    computed = hmac.new(
        app_secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, expected_hex)


def verify_twilio_signature(
    *, full_url: str, form_params: dict[str, str], signature: str, auth_token: str,
) -> bool:
    """HMAC-SHA1 verification per Twilio's X-Twilio-Signature header.

    Twilio's algorithm: full URL + sorted form params concatenated,
    HMAC-SHA1 with auth_token, base64-encoded.
    """
    sorted_params = sorted(form_params.items())
    canonical = full_url + "".join(f"{k}{v}" for k, v in sorted_params)
    digest = hmac.new(
        auth_token.encode("utf-8"),
        msg=canonical.encode("utf-8"),
        digestmod=hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def verify_meta_get_challenge(*, mode: str, token: str, challenge: str) -> str | None:
    """Handle Meta's GET-verification handshake.

    Meta sends GET ?hub.mode=subscribe&hub.verify_token=X&hub.challenge=Y.
    Webhook must reply with the challenge value if token matches.
    Returns the challenge string when valid, None otherwise.
    """
    if mode != "subscribe":
        return None
    if not WHATSAPP_VERIFY_TOKEN:
        return None
    if not hmac.compare_digest(token, WHATSAPP_VERIFY_TOKEN):
        return None
    return challenge


# ─── Outbound formatters ─────────────────────────────────────────


def format_outbound_meta(msg: OutboundMessage) -> dict[str, Any]:
    """Format OutboundMessage as Meta Graph API request body.

    POST https://graph.facebook.com/v18.0/{phone-id}/messages
    """
    body: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": msg.to_number,
        "type": "text",
        "text": {"body": msg.text, "preview_url": False},
    }
    if msg.reply_to_message_id:
        body["context"] = {"message_id": msg.reply_to_message_id}
    return body


def format_outbound_twilio(msg: OutboundMessage) -> dict[str, str]:
    """Format OutboundMessage as Twilio API form params.

    POST https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json
    """
    return {
        "To": f"whatsapp:{msg.to_number}",
        "Body": msg.text,
    }


def handle_inbound(payload: dict[str, Any], *, provider: str | None = None) -> InboundMessage | None:
    """Stage-1 dispatcher: normalize inbound based on provider env or arg.

    Returns InboundMessage on text message, None on non-message events.
    Raises WhatsAppWebhookDisabled when env flag unset (caller should
    return 200 OK without processing).
    """
    if not is_available():
        raise WhatsAppWebhookDisabled(
            "WhatsApp webhook disabled. Set WHATSAPP_WEBHOOK_ENABLED=1."
        )
    chosen = (provider or WHATSAPP_PROVIDER).lower()
    if chosen == "meta":
        return normalize_meta_webhook(payload)
    if chosen == "twilio":
        return normalize_twilio_webhook(payload)
    log.warning("unknown WhatsApp provider: %s", chosen)
    return None


if __name__ == "__main__":
    import json
    import sys
    print("scripts/whatsapp_webhook.py — Stage-1 WhatsApp gateway")
    print("Stage-1 opt-in via WHATSAPP_WEBHOOK_ENABLED=1")
    print("Supports Meta Cloud API + Twilio Business API")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
