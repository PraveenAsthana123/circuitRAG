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

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

log = logging.getLogger("mcp.server_common")


# ---------------------------------------------------------------------------
# Optional Prometheus — we expose per-tool call counters via /metrics.
# Guarded by try/except so mcp/ stays consumable without prometheus_client
# installed.
# ---------------------------------------------------------------------------
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter as _PromCounter,
        Histogram as _PromHistogram,
        generate_latest,
    )
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False


if _PROM_AVAILABLE:
    _TOOL_CALLS = _PromCounter(
        "documind_mcp_tool_calls_total",
        "Count of MCP /tools/call invocations by outcome",
        labelnames=["namespace", "tool", "outcome"],
    )
    # Per-tool latency histogram. Buckets tuned for tool calls that
    # mostly land between 5ms (cache replay) and ~5s (LLM-backed
    # tools); +Inf catches the long tail. Operators read p95/p99 per
    # (namespace, tool) — the primitive the per-tool dashboard panel
    # in the gap-review Phase 1 needs.
    _TOOL_LATENCY = _PromHistogram(
        "documind_mcp_tool_call_duration_seconds",
        "Wall-clock duration of MCP /tools/call dispatch by (namespace, tool).",
        labelnames=["namespace", "tool"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    # Scope-denial counter. reason ∈ {NOT_AUTHENTICATED, INVALID_TOKEN,
    # INSUFFICIENT_SCOPE}. Operators alert on per-tool denial rate
    # spikes — a sudden surge means either a token-rotation gap or a
    # caller-config drift. Without this counter, denials only show up
    # in logs and there's no rate-of-denial signal.
    _SCOPE_DENIALS = _PromCounter(
        "documind_mcp_scope_denials_total",
        "MCP scope/auth rejections by (namespace, tool, reason).",
        labelnames=["namespace", "tool", "reason"],
    )


def _record_tool_call(*, namespace: str, tool: str, outcome: str) -> None:
    """Called by handle_tool_call once per invocation.

    outcome ∈ {"ok", "degraded", "replay", "error"}. Replay is the
    idempotent-cache hit path — distinct from "ok" because it's
    free from an infra cost perspective and useful to know about
    separately.
    """
    if _PROM_AVAILABLE:
        _TOOL_CALLS.labels(namespace=namespace, tool=tool, outcome=outcome).inc()


def _observe_tool_latency(*, namespace: str, tool: str, seconds: float) -> None:
    if _PROM_AVAILABLE:
        _TOOL_LATENCY.labels(namespace=namespace, tool=tool).observe(seconds)


def _record_scope_denial(*, namespace: str, tool: str, reason: str) -> None:
    if _PROM_AVAILABLE:
        _SCOPE_DENIALS.labels(namespace=namespace, tool=tool, reason=reason).inc()


def _denial_reason(exc: HTTPException) -> str:
    """Map an HTTPException raised by enforce_scope to a stable
    Prometheus label value. Defends against detail-shape drift —
    if a new code is added we get ``UNKNOWN`` rather than a
    label-cardinality blow-up."""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else None
    return code if code in {
        "NOT_AUTHENTICATED", "INVALID_TOKEN", "INSUFFICIENT_SCOPE",
    } else "UNKNOWN"


def mount_metrics_endpoint(app: FastAPI) -> None:
    """Mount a minimal GET /metrics on the app. Returns the default
    prometheus_client registry in its text exposition format.
    No-op when prometheus_client isn't installed."""
    if not _PROM_AVAILABLE:
        return

    @app.get("/metrics", include_in_schema=False)
    async def _metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )


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


# ---------------------------------------------------------------------------
# Canonical /tools/call handler — extracts the wrap-logic identical
# across every MCP server. A server provides its tool catalog, its
# idempotency cache dict, and a dispatch coroutine; this function
# handles correlation_id synthesis, scope check (before-cache to
# prevent leaked-idempotency-key replay), OTel span with standard
# attributes, and idempotency cache lookup/return.
# ---------------------------------------------------------------------------
async def handle_tool_call(  # noqa: PLR0913 — deliberate: one big helper
    *,
    req: "ToolCallRequest",
    tools: list[dict[str, Any]],
    idempotency_key: str | None,
    authorization: str | None,
    auth_required: bool,
    verifier: TokenVerifier | None,
    # ``idempotency_store`` replaces the previous ``idempotency_cache: dict``.
    # The store knows how to fingerprint payloads, detect same-key /
    # different-payload conflicts, and finalise on success or failure.
    # ``handle_tool_call`` stays dumb — get-or-record — see mcp/idempotency.py.
    idempotency_store: "Any",  # IdempotencyStore protocol; avoid circular import here
    dispatch,  # noqa: ANN001 — async callable(req, idempotency_key, cid) -> dict
    tracer_module: str,
    logger: logging.Logger,
    service_label: str,
) -> dict[str, Any]:
    import uuid as _uuid

    cid = req.correlation_id or str(_uuid.uuid4())
    logger.info(
        "%s_tool_called name=%s tenant=%s corr=%s idempotency=%s auth=%s",
        service_label, req.name, req.tenant_id, cid, idempotency_key,
        "yes" if authorization else "no",
    )

    # Scope BEFORE cache — prevents leaked-idempotency-key replays
    # from bypassing scope enforcement.
    if auth_required:
        tool = next((t for t in tools if t["name"] == req.name), None)
        if tool is None:
            # Authenticate first so unknown-name probes get 401 from
            # unauthenticated callers, 404 from authenticated ones.
            try:
                enforce_scope(
                    verifier, authorization,
                    {"name": req.name, "required_scopes": []},
                )
            except HTTPException as exc:
                _record_scope_denial(
                    namespace=service_label, tool=req.name,
                    reason=_denial_reason(exc),
                )
                raise
            raise HTTPException(
                status_code=404,
                detail={"code": "tool_not_found", "name": req.name},
            )
        try:
            enforce_scope(verifier, authorization, tool)
        except HTTPException as exc:
            _record_scope_denial(
                namespace=service_label, tool=req.name,
                reason=_denial_reason(exc),
            )
            raise

    tracer = get_tracer(tracer_module)
    span_cm = (
        tracer.start_as_current_span(f"mcp.tool:{req.name}")
        if tracer is not None
        else NoopCM()
    )

    with span_cm as sp:
        if OTEL_AVAILABLE and sp is not None:
            sp.set_attribute("mcp.tool.name", req.name)
            if req.tenant_id:
                sp.set_attribute("documind.tenant_id", req.tenant_id)
                sp.set_attribute("mcp.tenant_id", req.tenant_id)
            sp.set_attribute("documind.correlation_id", cid)
            sp.set_attribute("mcp.correlation_id", cid)
            sp.set_attribute(
                "mcp.idempotency_key_present", idempotency_key is not None,
            )

        # Idempotency lookup. The store handles payload fingerprinting,
        # in-progress / conflict detection, and TTL purging — this
        # function only translates the (state, response) tuple to the
        # right HTTP shape and metric outcome.
        from mcp.idempotency import fingerprint as _fingerprint

        if idempotency_key and idempotency_store is not None:
            fp = _fingerprint(req.arguments or {})
            state, cached = await idempotency_store.lookup_or_register(
                idempotency_key, req.name, fp,
            )
            if state == "done":
                logger.info(
                    "%s_idempotent_replay key=%s", service_label, idempotency_key,
                )
                if OTEL_AVAILABLE and sp is not None:
                    sp.set_attribute("mcp.idempotent_replay", True)
                _record_tool_call(
                    namespace=service_label, tool=req.name, outcome="replay",
                )
                return {**(cached or {}), "idempotent_replay": True}
            if state == "in_progress":
                # Don't wait — drill.run can take minutes; a waiting
                # client wedges the connection pool. 202 tells the
                # caller to come back later.
                logger.info(
                    "%s_idempotent_in_progress key=%s",
                    service_label, idempotency_key,
                )
                _record_tool_call(
                    namespace=service_label, tool=req.name, outcome="in_progress",
                )
                raise HTTPException(
                    status_code=202,
                    detail={
                        "code": "idempotency_in_progress",
                        "key": idempotency_key,
                        "message": (
                            "A call with this Idempotency-Key is still "
                            "running. Retry in a moment."
                        ),
                    },
                )
            if state == "conflict":
                logger.warning(
                    "%s_idempotency_conflict key=%s tool=%s",
                    service_label, idempotency_key, req.name,
                )
                _record_tool_call(
                    namespace=service_label, tool=req.name, outcome="conflict",
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "idempotency_conflict",
                        "key": idempotency_key,
                        "message": (
                            "This Idempotency-Key was previously used with "
                            "a different request payload. Use a new key or "
                            "send the original payload."
                        ),
                    },
                )
            # state == "new" → caller proceeds; we finalise after.

        # Time only the real dispatch path — cache replays returned
        # above are accounted for via outcome="replay" on the call
        # counter. Failed dispatches still record latency: an op
        # alert on rising p95 wants to see slow-failures, not just
        # slow-successes.
        import time as _time
        _started = _time.perf_counter()
        try:
            response = await dispatch(req, idempotency_key, cid)
        except HTTPException as exc:
            _observe_tool_latency(
                namespace=service_label, tool=req.name,
                seconds=_time.perf_counter() - _started,
            )
            # 4xx from dispatch (e.g. 404 tool_not_found inside dispatch) —
            # surface as "error" since a 5xx-shaped outcome isn't what
            # happened. Upstream HTTPException raised from enforce_scope
            # already incremented nothing because we never got here.
            if idempotency_key and idempotency_store is not None:
                # Record as 'failed' so the row doesn't linger as
                # in_progress (a future retry would 202 forever).
                # Best-effort: don't shadow the original exception.
                try:
                    await idempotency_store.finalize(
                        idempotency_key,
                        {"ok": False, "error": {"http_status": exc.status_code}},
                        status="failed",
                    )
                except Exception:  # noqa: BLE001 — finalize must not shadow the dispatch error
                    pass
            _record_tool_call(
                namespace=service_label, tool=req.name,
                outcome=f"http_{exc.status_code}",
            )
            raise

        _observe_tool_latency(
            namespace=service_label, tool=req.name,
            seconds=_time.perf_counter() - _started,
        )
        if idempotency_key and idempotency_store is not None:
            await idempotency_store.finalize(idempotency_key, response, status="succeeded")

        outcome = "ok" if response.get("ok") else "error"
        _record_tool_call(namespace=service_label, tool=req.name, outcome=outcome)
        return response


__all__ = [
    "OTEL_AVAILABLE",
    "JWT_AVAILABLE",
    "NoopCM",
    "ToolCallRequest",
    "TokenVerifier",
    "build_auth",
    "enforce_scope",
    "get_tracer",
    "handle_tool_call",
    "mount_metrics_endpoint",
    "setup_server_otel",
]
