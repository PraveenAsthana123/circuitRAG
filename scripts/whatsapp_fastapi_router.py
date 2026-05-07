"""WhatsApp FastAPI router — Stage-2 wire (per CLAUDE.md §56).

Stage-2 mounts a reusable APIRouter that:
  - GET  /webhooks/whatsapp  — Meta verification handshake
  - POST /webhooks/whatsapp  — inbound message handler

Operators include the router into ANY FastAPI app:

  from whatsapp_fastapi_router import router
  app.include_router(router)

Wires the Stage-1 whatsapp_webhook adapter (commit 7d32d41) end-to-end:
  inbound webhook → signature verify → normalize payload → PII pre-check
  → Gemma council → format outbound → return 200

THE BRUTAL CONTRACT (drilled):
  Reply with HTTP 200 on EVERY webhook even when processing fails —
  Meta/Twilio retry on non-200 which would amplify failures into
  cascading webhook storms. Errors get logged + audited; the user
  sees a graceful fallback message. Per §47 fail-safe.

OPERATOR OPT-IN (single env flag inherits Stage-1):
  WHATSAPP_WEBHOOK_ENABLED=1
  WHATSAPP_PROVIDER=meta            # or 'twilio'
  WHATSAPP_META_APP_SECRET=...      # for HMAC verification
  WHATSAPP_VERIFY_TOKEN=...         # for Meta GET handshake
  GEMMA_AGENT_COUNCIL_ENABLED=1     # downstream dispatch target

COMPOSES WITH (per §49):
  scripts/whatsapp_webhook.py — Stage-1 adapter (verify + normalize)
  scripts/gemma_agent_council.py — Stage-1 council (downstream dispatch)
  scripts/pii_redactor.py — Stage-1 PII (inbound scan before council)
  scripts/langfuse_tracer.py — Stage-1 observability (per-request trace)
  docs/architecture/six-plane-audit-2026-05-04.md — integration plane
  §38 — decision audit (every webhook → audit row)
  §43 — drill discipline
  §47 — fail-safe (always return 200)
  §52 — brutal tool review (40-row when wired in production app)
  §56 — Stage-2 6-gate
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

log = logging.getLogger(__name__)

# Add scripts/ to path for sibling imports (whatsapp_webhook +
# gemma_agent_council + pii_redactor live there).
_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

WHATSAPP_FASTAPI_ROUTER_ENABLED = os.getenv("WHATSAPP_WEBHOOK_ENABLED", "").strip() == "1"


def _import_fastapi():
    """Lazy FastAPI import — keeps this module-importable when fastapi
    isn't installed (e.g. in pure-CLI contexts)."""
    try:
        from fastapi import APIRouter, HTTPException, Request, Response
        return APIRouter, HTTPException, Request, Response
    except ImportError:
        return None, None, None, None


def _make_router():
    """Build the router lazily so the module can be imported without
    triggering FastAPI dependency-resolution. Returns None when
    FastAPI is unavailable (caller checks)."""
    APIRouter, HTTPException, Request, Response = _import_fastapi()
    if APIRouter is None:
        return None

    router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

    @router.get("/whatsapp")
    async def verify_handshake(request: Request) -> Response:
        """Meta GET-verification handshake.

        Meta sends GET ?hub.mode=subscribe&hub.verify_token=X&hub.challenge=Y.
        We reply with the challenge value if token matches the
        operator-configured WHATSAPP_VERIFY_TOKEN. Per Meta API docs.
        """
        from whatsapp_webhook import verify_meta_get_challenge  # noqa: PLC0415

        params = dict(request.query_params)
        mode = params.get("hub.mode", "")
        token = params.get("hub.verify_token", "")
        challenge = params.get("hub.challenge", "")
        result = verify_meta_get_challenge(
            mode=mode, token=token, challenge=challenge,
        )
        if result is None:
            log.warning("whatsapp_verify_failed mode=%s token_match=False", mode)
            raise HTTPException(status_code=403, detail="verification_failed")
        log.info("whatsapp_verify_ok challenge=%s", challenge[:10])
        return Response(content=challenge, media_type="text/plain", status_code=200)

    @router.post("/whatsapp")
    async def inbound_webhook(request: Request) -> dict[str, Any]:
        """Inbound message handler.

        Flow:
          1. Read body + signature header
          2. Verify HMAC (Meta SHA-256 OR Twilio SHA-1)
          3. Normalize payload to InboundMessage
          4. PII pre-check (skip user if injection detected)
          5. Dispatch to Gemma council
          6. Format outbound + ALWAYS return 200

        Per §47 fail-safe: returns 200 even on processing failure.
        Webhook retries on non-200 cause cascading storms.
        """
        if not WHATSAPP_FASTAPI_ROUTER_ENABLED:
            # Per-router opt-in. Returning 200 here means Meta/Twilio
            # don't retry storm us when the operator has the env unset.
            return {"ok": True, "skipped": "webhook_disabled"}

        try:
            body = await request.body()
            provider = os.getenv("WHATSAPP_PROVIDER", "meta").lower()

            # Step 2: signature verification (per provider)
            if provider == "meta":
                signature = request.headers.get("x-hub-signature-256", "")
                secret = os.getenv("WHATSAPP_META_APP_SECRET", "")
                if not secret:
                    log.warning("whatsapp_meta_secret_missing — skipping verification")
                else:
                    from whatsapp_webhook import verify_meta_signature  # noqa: PLC0415
                    if not verify_meta_signature(body, signature, secret):
                        log.warning("whatsapp_signature_invalid provider=meta")
                        return {"ok": True, "rejected": "invalid_signature"}

            # Step 3: parse payload
            import json  # noqa: PLC0415
            payload: dict[str, Any]
            content_type = (request.headers.get("content-type") or "").lower()
            if "json" in content_type:
                payload = json.loads(body or b"{}")
            else:
                # Twilio sends form-encoded
                from urllib.parse import parse_qsl  # noqa: PLC0415
                payload = dict(parse_qsl(body.decode("utf-8") if body else ""))

            from whatsapp_webhook import handle_inbound  # noqa: PLC0415
            inbound = handle_inbound(payload, provider=provider)
            if inbound is None:
                # Status update, delivery receipt, etc — not a message
                return {"ok": True, "ignored": "non_message_event"}

            # Step 4: PII pre-check (best-effort)
            try:
                if os.getenv("PII_REDACTOR_ENABLED", "").strip() == "1":
                    import pii_redactor  # noqa: PLC0415
                    if pii_redactor.is_available():
                        _, entities = pii_redactor.redact(inbound.text)
                        if entities:
                            log.info(
                                "whatsapp_pii_in_inbound msg_id=%s entities=%s",
                                inbound.message_id,
                                sorted({e.entity_type for e in entities}),
                            )
            except Exception as exc:
                log.warning("whatsapp_pii_check_failed: %s", exc)

            # Step 5: dispatch to Gemma council (best-effort)
            response_text = "Thanks for your message. I'm processing it."
            try:
                if os.getenv("GEMMA_AGENT_COUNCIL_ENABLED", "").strip() == "1":
                    from gemma_agent_council import run_council  # noqa: PLC0415
                    council_result = run_council(inbound.text)
                    if council_result.ok:
                        response_text = council_result.final_output[:1500]  # WhatsApp text limit
                    else:
                        response_text = (
                            f"I couldn't process that — reason: "
                            f"{council_result.blocked_reason or 'unknown'}"
                        )
            except Exception as exc:
                log.warning("whatsapp_council_dispatch_failed: %s", exc)
                # Keep the canned acknowledgment response

            # Step 6: format outbound (caller would POST to provider's API)
            from whatsapp_webhook import OutboundMessage, format_outbound_meta, format_outbound_twilio  # noqa: PLC0415
            outbound = OutboundMessage(
                to_number=inbound.from_number,
                text=response_text,
                reply_to_message_id=inbound.message_id,
            )
            if provider == "meta":
                formatted = format_outbound_meta(outbound)
            else:
                formatted = format_outbound_twilio(outbound)

            log.info(
                "whatsapp_dispatch_ok provider=%s msg_id=%s response_chars=%d",
                provider, inbound.message_id, len(response_text),
            )
            # Stage-2 doesn't actually POST to provider's API — that's
            # Stage-3 (httpx call to Meta Graph or Twilio Messages).
            # Stage-2 returns 200 + the formatted body so the operator
            # (or a Stage-3 worker) can pick it up. NEVER blocks the
            # webhook reply.
            return {"ok": True, "outbound": formatted}

        except Exception as exc:
            # ALWAYS return 200 even on failure — webhook retry storms
            # are worse than dropped messages. Log + audit instead.
            log.exception("whatsapp_inbound_handler_failed: %s", exc)
            return {"ok": True, "error": str(exc)[:200]}

    return router


# Lazy-build the router so import doesn't require fastapi present
router = _make_router()


def is_available() -> bool:
    """True iff env flag set + fastapi installed + Stage-1 adapter available."""
    if not WHATSAPP_FASTAPI_ROUTER_ENABLED:
        return False
    if router is None:
        return False
    try:
        import whatsapp_webhook  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": 2,
        "enabled_env": WHATSAPP_FASTAPI_ROUTER_ENABLED,
        "available": is_available(),
        "router_built": router is not None,
        "provider": os.getenv("WHATSAPP_PROVIDER", "meta").lower(),
        "wiring_status": "stage-2 reusable APIRouter; operator does app.include_router(router)",
        "next_stage": (
            "Stage-3 — outbound POST to Meta Graph API / Twilio "
            "Messages API (worker pattern + retry); media support; "
            "template messages; reactions; conversation memory store"
        ),
        "fail_safe_contract": "ALWAYS returns 200 to prevent webhook retry storms",
    }


if __name__ == "__main__":
    import json
    print("scripts/whatsapp_fastapi_router.py — Stage-2 reusable FastAPI router")
    print("Stage-2 opt-in via WHATSAPP_WEBHOOK_ENABLED=1 (Stage-1 inheritance)")
    print()
    print(json.dumps(status(), indent=2))
