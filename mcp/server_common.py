"""
Shared scaffolding for MCP tool servers.

Why this module exists
======================

Every MCP server (``server_hr.py``, ``server_itsm.py``,
``server_drills.py``, ...) was independently implementing the same
four responsibilities:

1. Optional OTel wiring (trace provider, OTLP exporter, FastAPI
   instrumentation).
2. Optional JWT verification (RS256, iss/aud/exp/kind=access).
3. Per-tool scope enforcement on ``/tools/call``.
4. A ``_NoopCM`` placeholder so ``with <span_cm>`` works when OTel is
   absent.

With three servers the duplication was ~60 lines per file. This module
factors it out. Each server now does::

    from mcp.server_common import (
        setup_server_otel, build_auth, enforce_scope, NoopCM,
    )
    app = FastAPI(...)
    setup_server_otel(app, service_name="mcp-server-<ns>")
    AUTH_REQUIRED, VERIFIER = build_auth()

    # in /tools/call:
    if AUTH_REQUIRED:
        enforce_scope(VERIFIER, authorization, tool)

No change to wire format or public behaviour. Existing drills keep
passing; that's the regression safety net.

Decoupling contract — same as the rest of ``mcp/``: this module must
not import ``documind_core``. MCP servers are portable; a future
``mcp-server-standalone`` repo should be able to vendor just
``mcp/`` without pulling in the core lib.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

log = logging.getLogger("mcp.server_common")


# ---------------------------------------------------------------------------
# Wire-format request body — identical across every MCP server.
# Extracting it means all servers share one contract; a client
# library written against any one is compatible with all.
# ---------------------------------------------------------------------------
class ToolCallRequest(BaseModel):
    """Canonical body for POST /tools/call across every MCP server."""

    name: str
    arguments: dict[str, Any]
    tenant_id: str | None = None
    correlation_id: str | None = None


# ---------------------------------------------------------------------------
# OTel — optional. Silent no-op if the SDK isn't installed.
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OTEL_AVAILABLE = False


def setup_server_otel(app: FastAPI, *, service_name: str) -> None:
    """
    Wire OTel for one MCP server. Idempotent per process (TracerProvider
    is module-scoped in OTel; subsequent calls just add exporters).

    Reads ``DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT`` (default localhost:4317)
    and ``DOCUMIND_ENV`` (default development).
    """
    if not OTEL_AVAILABLE:
        log.info("mcp_server_otel_skipped service=%s reason=sdk_missing", service_name)
        return
    endpoint = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "documind",
        "deployment.environment": os.getenv("DOCUMIND_ENV", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)),
    )
    _otel_trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    log.info(
        "mcp_server_otel_initialized service=%s endpoint=%s",
        service_name, endpoint,
    )


def get_tracer(module_name: str):  # noqa: ANN201
    """Return an OTel tracer, or None if the SDK is unavailable."""
    if not OTEL_AVAILABLE:
        return None
    return _otel_trace.get_tracer(module_name)


# ---------------------------------------------------------------------------
# JWT verification — optional, opt-in via MCP_AUTH_REQUIRED=true.
# ---------------------------------------------------------------------------
try:
    import jwt as _pyjwt
    JWT_AVAILABLE = True
except ImportError:  # pragma: no cover
    JWT_AVAILABLE = False


class TokenVerifier:
    """RS256 verifier. Mirrors identity-svc's Issuer.Verify."""

    def __init__(
        self,
        *,
        public_key_path: str,
        issuer: str,
        audience: str,
        expected_kind: str = "access",
    ) -> None:
        self._pub = Path(public_key_path).read_bytes()
        self._iss = issuer
        self._aud = audience
        self._expected_kind = expected_kind

    @property
    def issuer(self) -> str:
        return self._iss

    @property
    def audience(self) -> str:
        return self._aud

    def verify(self, raw: str) -> dict[str, Any]:
        claims = _pyjwt.decode(
            raw,
            self._pub,
            algorithms=["RS256"],
            issuer=self._iss,
            audience=self._aud,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        if self._expected_kind and claims.get("kind") != self._expected_kind:
            raise _pyjwt.InvalidTokenError(
                f"wrong token kind: got {claims.get('kind')!r} "
                f"want {self._expected_kind!r}"
            )
        return claims


def build_auth() -> tuple[bool, TokenVerifier | None]:
    """
    Read env and return ``(auth_required, verifier_or_None)``.

    Env:
      * ``MCP_AUTH_REQUIRED`` (default "false")
      * ``MCP_JWT_PUBLIC_KEY_PATH`` overrides
        ``DOCUMIND_JWT_PUBLIC_KEY_PATH``
      * ``DOCUMIND_JWT_ISSUER`` (default "documind-local")
      * ``DOCUMIND_JWT_AUDIENCE`` (default "documind-services")

    Raises at import time if ``MCP_AUTH_REQUIRED=true`` but PyJWT
    isn't installed — a loud failure is correct here: we refuse to
    boot in "enforce" mode without the enforcement primitive.
    """
    auth_required = os.getenv("MCP_AUTH_REQUIRED", "false").lower() == "true"
    if not auth_required:
        return False, None
    if not JWT_AVAILABLE:
        raise RuntimeError(
            "MCP_AUTH_REQUIRED=true but PyJWT is not installed",
        )
    verifier = TokenVerifier(
        public_key_path=os.getenv(
            "MCP_JWT_PUBLIC_KEY_PATH",
            os.getenv(
                "DOCUMIND_JWT_PUBLIC_KEY_PATH",
                "./scripts/dev-keys/jwt-public.pem",
            ),
        ),
        issuer=os.getenv("DOCUMIND_JWT_ISSUER", "documind-local"),
        audience=os.getenv("DOCUMIND_JWT_AUDIENCE", "documind-services"),
    )
    log.info(
        "mcp_auth_required=true issuer=%s audience=%s",
        verifier.issuer, verifier.audience,
    )
    return True, verifier


def enforce_scope(
    verifier: TokenVerifier | None,
    authorization: str | None,
    tool: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate the caller's JWT and intersect ``roles`` with the tool's
    ``required_scopes``. Returns the claims dict on success. Raises
    ``HTTPException(401|403)`` otherwise.

    No-op (returns ``{}``) when ``verifier`` is None — auth is off.
    """
    if verifier is None:
        return {}
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"code": "NOT_AUTHENTICATED", "message": "Bearer token required"},
        )
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"code": "NOT_AUTHENTICATED", "message": "malformed Authorization header"},
        )
    try:
        claims = verifier.verify(parts[1].strip())
    except _pyjwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc
    required = set(tool.get("required_scopes") or [])
    if not required:
        return claims
    have = set(claims.get("roles") or [])
    if required.isdisjoint(have):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_SCOPE",
                "required": sorted(required),
                "have": sorted(have),
                "tool": tool.get("name"),
            },
        )
    return claims


# ---------------------------------------------------------------------------
# Tiny helpers every server uses.
# ---------------------------------------------------------------------------
class NoopCM:
    """Context-manager placeholder returned when OTel isn't available.
    Lets callers write ``with span_cm as sp:`` unconditionally."""

    def __enter__(self):  # noqa: ANN204
        return None

    def __exit__(self, *a):  # noqa: ANN204
        return False


__all__ = [
    "OTEL_AVAILABLE",
    "JWT_AVAILABLE",
    "NoopCM",
    "ToolCallRequest",
    "TokenVerifier",
    "build_auth",
    "enforce_scope",
    "get_tracer",
    "setup_server_otel",
]
