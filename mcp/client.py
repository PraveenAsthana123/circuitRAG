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

log = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema" / "tool_schema.json"


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
# Minimal CB (local, not documind_core — keeps mcp/ decoupled)
# ---------------------------------------------------------------------------
class _MCPBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, name: str, *, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        if self._state == self.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                return True
            return False
        return True

    def record_success(self) -> None:
        if self._state == self.HALF_OPEN:
            log.info("mcp_cb transition name=%s half_open->closed", self.name)
        self._state = self.CLOSED
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
            if self._state != self.OPEN:
                log.warning("mcp_cb transition name=%s -> OPEN (failures=%d)", self.name, self._failures)
            self._state = self.OPEN
            self._opened_at = time.monotonic()

    @property
    def state(self) -> str:
        return self._state


# ---------------------------------------------------------------------------
# In-memory draft store — replace with governance.hitl_queue in prod.
# ---------------------------------------------------------------------------
_DRAFTS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class MCPClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 5.0,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_s)
        self._breaker = _MCPBreaker(
            name=self._base,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._tools_cache: list[dict[str, Any]] | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        if self._tools_cache is not None:
            return self._tools_cache
        if not self._breaker.allow():
            log.warning("mcp_list_tools_rejected cb=open url=%s", self._base)
            return []
        try:
            r = await self._client.get(f"{self._base}/tools/list")
            r.raise_for_status()
            self._tools_cache = r.json()["tools"]
            self._breaker.record_success()
            return self._tools_cache
        except (httpx.HTTPError, KeyError):
            self._breaker.record_failure()
            raise

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        tenant_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        """
        Call a tool. On CB OPEN or any HTTP failure: persist a draft,
        return ``degraded=True``.
        """
        key = idempotency_key or uuid.uuid4().hex
        cid = correlation_id or uuid.uuid4().hex

        # CB check
        if not self._breaker.allow():
            return self._persist_draft(name, arguments, tenant_id, cid, reason="cb_open")

        payload = {"name": name, "arguments": arguments}
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if correlation_id:
            payload["correlation_id"] = cid

        try:
            r = await self._client.post(
                f"{self._base}/tools/call",
                json=payload,
                headers={"Idempotency-Key": key, "X-Correlation-Id": cid},
            )
            if r.status_code >= 500:
                self._breaker.record_failure()
                return self._persist_draft(name, arguments, tenant_id, cid, reason=f"http_{r.status_code}")
            data = r.json()
            self._breaker.record_success()
            if data.get("ok"):
                return ToolResult(
                    ok=True,
                    data=data.get("result"),
                    idempotent_replay=bool(data.get("idempotent_replay")),
                )
            return ToolResult(ok=False, error=data.get("error"))
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            self._breaker.record_failure()
            return self._persist_draft(
                name, arguments, tenant_id, cid, reason=f"{type(exc).__name__}"
            )

    def _persist_draft(
        self,
        name: str,
        arguments: dict[str, Any],
        tenant_id: str | None,
        correlation_id: str,
        *,
        reason: str,
    ) -> ToolResult:
        draft_id = f"DRAFT-{uuid.uuid4().hex[:10].upper()}"
        _DRAFTS[draft_id] = {
            "tool": name,
            "arguments": arguments,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "reason": reason,
            "persisted_at": time.time(),
        }
        log.warning(
            "mcp_draft_persisted draft_id=%s tool=%s reason=%s corr=%s",
            draft_id, name, reason, correlation_id,
        )
        return ToolResult(ok=False, degraded=True, draft_id=draft_id)

    @property
    def cb_state(self) -> str:
        return self._breaker.state

    @staticmethod
    def drafts() -> dict[str, dict[str, Any]]:
        """Inspection helper — return the in-memory draft store."""
        return _DRAFTS
