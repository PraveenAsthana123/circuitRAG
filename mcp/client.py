"""
MCP client — call remote tools over HTTP with CB + idempotency + draft fallback.

Design
------
* **Circuit breaker** around every tool call. OPEN = MCP server down; agent
  persists a *draft* action instead of making the call. Classic
  Phase-6-scenario-13 pattern.
* **Idempotency**: client generates + sends an ``Idempotency-Key``. If the
  same action is retried (e.g. after a flaky network), the server replays
  the cached response instead of executing twice.
* **JSON Schema validation** against ``schema/tool_schema.json`` so the
  caller never invents arguments the server cannot parse.

Usage::

    client = MCPClient(base_url="http://127.0.0.1:8090")
    result = await client.call_tool(
        "hr.leave_request",
        {"employee_id": "E123", "days": 3, "reason": "family event"},
        tenant_id="acme",
    )
    if result.ok:
        print("submitted:", result.data["ticket_id"])
    elif result.degraded:
        print("draft persisted:", result.draft_id)
    else:
        print("failed:", result.error)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from documind_core.circuit_breaker import CircuitBreaker

from .drafts import DraftRecord, DraftStore, InMemoryDraftStore

log = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema" / "tool_schema.json"


def _normalise_error(data: Any, status_code: int) -> dict[str, Any]:
    """
    Map a 4xx response body into the ``ToolResult.error`` envelope.

    * ``{"error": {...}}`` — our own protocol: return the error dict as-is.
    * ``{"detail": {...}}`` — FastAPI HTTPException: lift ``detail`` into
      ``error``, add ``http_status`` for unambiguous operator logs.
    * ``{"detail": "<string>"}`` — wrap in a code/message dict so
      callers always see a structured shape.
    * Anything else — store the raw body under ``error.body``.
    """
    if isinstance(data, dict):
        if data.get("error") is not None:
            err = dict(data["error"])
            err.setdefault("http_status", status_code)
            return err
        detail = data.get("detail")
        if isinstance(detail, dict):
            err = dict(detail)
            err.setdefault("http_status", status_code)
            return err
        if isinstance(detail, str):
            return {
                "code": "HTTP_" + str(status_code),
                "message": detail,
                "http_status": status_code,
            }
    return {
        "code": "HTTP_" + str(status_code),
        "http_status": status_code,
        "body": data,
    }


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------
@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    degraded: bool = False  # true when CB OPEN → draft persisted
    draft_id: str | None = None
    idempotent_replay: bool = False


# ---------------------------------------------------------------------------
# Breaker — unified with documind_core.circuit_breaker.CircuitBreaker.
# Earlier iterations kept a private ``_MCPBreaker`` here "for decoupling,"
# which silently forked behavior: the local copy was lockless, didn't
# emit failure/open/rejection counters, and had no transition accounting.
# Now mcp/ uses the canonical breaker via the ``allow/record_success/
# record_failure`` bool-return API added for this file's call shape (see
# documind_core/circuit_breaker.py — the methods are documented there).
# One state machine, one metric model, one set of semantics.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class MCPClient:
    def __init__(
        self,
        *,
        base_url: str,
        breaker_name: str | None = None,
        timeout_s: float = 5.0,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        draft_store: DraftStore | None = None,
        audit_log: Any = None,
        tools_cache_ttl_s: float = 60.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_s)
        # Canonical breaker. The lifespan should pass ``breaker_name``
        # using the stable ``mcp_<namespace>`` scheme (mcp_hr, mcp_itsm)
        # so the URL-keyed series the breaker emits matches what
        # BreakerMetricsExporter pushes for /health/detailed. Without
        # the override the breaker labels by URL — fine for ad-hoc
        # tests, but in production it produces a duplicate Prometheus
        # series alongside the canonical ``mcp_<ns>`` one.
        self._breaker = CircuitBreaker(
            name=breaker_name or self._base,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        # Bounded cache — without a TTL, a change to the MCP server's
        # tool catalog (new tool, updated required_scopes) silently
        # goes unpicked-up until the agent restarts, which means the
        # scope-pre-check enforces stale policy. 60s default is a
        # reasonable window for a governance surface that doesn't
        # change under load; tighten via ctor for tests.
        self._tools_cache: list[dict[str, Any]] | None = None
        self._tools_cache_fetched_at: float = 0.0
        self._tools_cache_ttl_s = max(0.0, tools_cache_ttl_s)
        # Observable: how many times we ACTUALLY hit the server for
        # the tools list. Tests assert this doesn't increment on
        # cache hits, and DOES increment after TTL expiry.
        self._tools_fetch_count: int = 0
        # DraftStore is duck-typed; defaults to in-memory for tests and
        # environments without a database. Production services pass a
        # PostgresDraftStore from their lifespan.
        self._drafts: DraftStore = draft_store or InMemoryDraftStore()
        # AuditLog is optional. When wired, every draft.created /
        # draft.replayed transition produces a hash-chained row in
        # governance.audit_log. When not, callers behave as before.
        self._audit = audit_log

    async def close(self) -> None:
        await self._client.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        if (
            self._tools_cache is not None
            and time.monotonic() - self._tools_cache_fetched_at
            < self._tools_cache_ttl_s
        ):
            return self._tools_cache
        if not self._breaker.allow():
            # If the CB is open and we have a stale cache, return it
            # anyway — over-permissive-vs-stale is a trade-off, and
            # serving stale tool metadata beats failing every
            # /list_tools call during an outage. The worst case is the
            # agent pre-checks against a scope that no longer exists;
            # the MCP server would still reject at the enforcement
            # layer once it recovered.
            if self._tools_cache is not None:
                log.warning(
                    "mcp_list_tools_stale cb=open serving age=%.1fs url=%s",
                    time.monotonic() - self._tools_cache_fetched_at,
                    self._base,
                )
                return self._tools_cache
            log.warning("mcp_list_tools_rejected cb=open url=%s", self._base)
            return []
        try:
            r = await self._client.get(f"{self._base}/tools/list")
            r.raise_for_status()
            self._tools_cache = r.json()["tools"]
            self._tools_cache_fetched_at = time.monotonic()
            self._tools_fetch_count += 1
            self._breaker.record_success()
            return self._tools_cache
        except (httpx.HTTPError, KeyError):
            self._breaker.record_failure()
            raise

    @property
    def tools_fetch_count(self) -> int:
        """How many times we've actually round-tripped to /tools/list.
        Cache hits do NOT increment this; cache miss or TTL expiry do.
        """
        return self._tools_fetch_count

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        tenant_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        auth_token: str | None = None,
    ) -> ToolResult:
        """
        Call a tool. On CB OPEN or any HTTP failure: persist a draft,
        return ``degraded=True``.

        ``auth_token`` is forwarded as ``Authorization: Bearer ...`` so
        the MCP server can enforce per-tool scopes defence-in-depth.
        If not supplied, no Authorization header is sent (fine when MCP
        runs with MCP_AUTH_REQUIRED=false).
        """
        key = idempotency_key or uuid.uuid4().hex
        cid = correlation_id or uuid.uuid4().hex

        # CB check
        if not self._breaker.allow():
            return await self._persist_draft(name, arguments, tenant_id, cid, reason="cb_open")

        payload = {"name": name, "arguments": arguments}
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if correlation_id:
            payload["correlation_id"] = cid

        headers = {"Idempotency-Key": key, "X-Correlation-Id": cid}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            r = await self._client.post(
                f"{self._base}/tools/call",
                json=payload,
                headers=headers,
            )
            if r.status_code >= 500:
                self._breaker.record_failure()
                return await self._persist_draft(name, arguments, tenant_id, cid, reason=f"http_{r.status_code}")

            # Client-side error (400-499): server is healthy and responding,
            # so record_success() from the breaker's perspective (MCP is
            # reachable), but surface the structured reason to the caller.
            # FastAPI wraps HTTPException bodies as ``{"detail": <payload>}``;
            # our tool protocol uses ``{"ok": ..., "error": ...}``. Normalise
            # both so ``ToolResult.error`` is always populated on 4xx.
            data = r.json()
            self._breaker.record_success()
            if r.status_code >= 400:
                return ToolResult(
                    ok=False,
                    error=_normalise_error(data, r.status_code),
                )
            if data.get("ok"):
                return ToolResult(
                    ok=True,
                    data=data.get("result"),
                    idempotent_replay=bool(data.get("idempotent_replay")),
                )
            # 2xx with ok=false — legit business rejection from the server.
            return ToolResult(ok=False, error=data.get("error"))
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            self._breaker.record_failure()
            return await self._persist_draft(
                name, arguments, tenant_id, cid, reason=f"{type(exc).__name__}"
            )

    async def _persist_draft(
        self,
        name: str,
        arguments: dict[str, Any],
        tenant_id: str | None,
        correlation_id: str,
        *,
        reason: str,
    ) -> ToolResult:
        draft_id = f"DRAFT-{uuid.uuid4().hex[:10].upper()}"
        record = DraftRecord(
            draft_id=draft_id,
            tool=name,
            arguments=arguments,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            reason=reason,
        )
        try:
            await self._drafts.save(record)
        except Exception as exc:  # noqa: BLE001 — persistence must not shadow the degradation signal
            log.error(
                "mcp_draft_persist_failed draft_id=%s tool=%s err=%s — returning degraded anyway",
                draft_id, name, exc,
            )
        log.warning(
            "mcp_draft_persisted draft_id=%s tool=%s reason=%s corr=%s",
            draft_id, name, reason, correlation_id,
        )
        if self._audit is not None and tenant_id:
            await self._audit.write(
                tenant_id=tenant_id,
                action="mcp_draft.created",
                resource_type="mcp_draft",
                details={
                    "draft_id": draft_id,
                    "tool": name,
                    "reason": reason,
                    "cb_state": self._breaker.state,
                },
                correlation_id=correlation_id,
            )
        return ToolResult(ok=False, degraded=True, draft_id=draft_id)

    async def resolve_draft(
        self,
        draft_id: str,
        *,
        tenant_id: str | None = None,
        idempotency_key: str | None = None,
        auth_token: str | None = None,
        actor_type: str = "service",
        actor_id: str | None = None,
    ) -> ToolResult:
        """
        Replay a previously-persisted draft once the MCP server is back.

        Fetches the draft, re-invokes :meth:`call_tool` with the original
        args (preserving correlation_id), and on success marks the draft
        ``replayed`` with the result stored in ``replay_result``.
        If the replay itself fails, the *new* degraded response is
        returned; the original draft stays ``pending``.

        ``tenant_id`` is required for RLS-enforced backends (Postgres).
        ``actor_type`` + ``actor_id`` propagate into the audit row so
        governance reviews can distinguish a human operator replay
        (actor_type="operator", actor_id=<user UUID>) from an
        autonomous worker (actor_type="worker", actor_id=None) from
        generic service calls (actor_type="service").
        """
        record = await self._drafts.get(draft_id, tenant_id)
        if record is None:
            return ToolResult(ok=False, error={"code": "DRAFT_NOT_FOUND", "draft_id": draft_id})
        if record.status != "pending":
            return ToolResult(
                ok=False,
                error={"code": "DRAFT_NOT_PENDING", "status": record.status},
            )
        result = await self.call_tool(
            record.tool,
            record.arguments,
            tenant_id=record.tenant_id,
            correlation_id=record.correlation_id,
            idempotency_key=idempotency_key or draft_id,  # deterministic replay
            auth_token=auth_token,
        )
        if result.ok and result.data is not None:
            # CAS — only one replayer wins. If we lost the race (another
            # operator/worker already transitioned this draft), skip the
            # duplicate audit row + leave the result envelope ok=True
            # because the side-effect (ticket created) is real, just not
            # owned by us.
            transitioned = await self._drafts.mark_replayed(
                draft_id, result.data, record.tenant_id,
            )
            if transitioned and self._audit is not None and record.tenant_id:
                await self._audit.write(
                    tenant_id=record.tenant_id,
                    action="mcp_draft.replayed",
                    actor_type=actor_type,
                    actor_id=actor_id,
                    resource_type="mcp_draft",
                    details={
                        "draft_id": draft_id,
                        "tool": record.tool,
                        "result": result.data,
                        "idempotent_replay": result.idempotent_replay,
                    },
                    correlation_id=record.correlation_id,
                )
        return result

    async def list_pending_drafts(
        self, tenant_id: str | None = None
    ) -> list[DraftRecord]:
        return await self._drafts.list_pending(tenant_id)

    async def get_draft(
        self, draft_id: str, tenant_id: str | None = None
    ) -> DraftRecord | None:
        """
        Fetch a draft without replaying it. Useful for callers that need
        the tool name (to enforce a tool-derived scope) before deciding
        whether the user is allowed to resolve.
        """
        return await self._drafts.get(draft_id, tenant_id)

    @property
    def cb_state(self) -> str:
        # CircuitBreaker.state is a StrEnum (``State.OPEN`` etc.). Dashboards
        # and /health/detailed expect a plain ``"closed"|"open"|"half_open"``
        # string and serialise via JSON, so we normalise here. ``StrEnum``
        # equality already works against string literals, but ``json.dumps``
        # on a StrEnum can serialise as "State.OPEN" depending on the
        # encoder — explicit ``.value`` keeps the wire shape stable.
        s = self._breaker.state
        return s.value if hasattr(s, "value") else str(s)

    @property
    def draft_store(self) -> DraftStore:
        return self._drafts
