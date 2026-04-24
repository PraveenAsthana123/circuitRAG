"""
Agent flow: answer + optional MCP action.

The minimum-viable agent (good enough to prove the end-to-end pattern):

1. Always call the RAG pipeline (retrieve + generate) first so the answer is
   grounded.
2. Run rule-based intent detection on the query to decide whether an MCP
   tool should fire. Real production would use the LLM itself to pick the
   tool + extract args — but a regex is sufficient to prove the plumbing.
3. If an action matches AND ``allow_actions=True`` AND the employee_id is
   provided, call the MCP tool via ``mcp.MCPClient``.
4. Return ``AgentAskResponse`` with both ``answer`` (grounded, cited) and
   ``action`` (tool name + result or draft_id on CB OPEN).

Security note: in production, the scope check happens here against the
JWT-derived role; we defer that to an explicit follow-up (tracked as a
gap in docs/DEMO-DAY-3-MCP.md).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from documind_core.auth import required_role_for_tool
from documind_core.breakers import record_agent_denial
from mcp import MCPClient
from mcp.client import ToolResult

from app.schemas import (
    AgentAction,
    AgentAskRequest,
    AgentAskResponse,
    AskRequest,
)
from app.services.rag_inference import RagInferenceService

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule-based intent matcher. Real impl: swap for LLM-driven tool selection.
# ---------------------------------------------------------------------------
_LEAVE_PATTERN = re.compile(
    r"\b(submit|request|take|book|file)\b.*\b(\d+)[-\s]?day[s]?\b.*\bleave\b",
    re.IGNORECASE,
)
_POLICY_PATTERN = re.compile(
    r"\b(lookup|look up|show|fetch|get)\b.*\b(leave|travel|expense)\s+policy\b",
    re.IGNORECASE,
)
_INCIDENT_OPEN_PATTERN = re.compile(
    r"\b(open|file|create|raise|log)\b.*\b(incident|ticket|issue)\b",
    re.IGNORECASE,
)


@dataclass
class DetectedIntent:
    tool: str
    arguments: dict[str, Any]


def _detect_intent(query: str, employee_id: str | None) -> DetectedIntent | None:
    m = _LEAVE_PATTERN.search(query)
    if m and employee_id:
        days = int(m.group(2))
        return DetectedIntent(
            tool="hr.leave_request",
            arguments={
                "employee_id": employee_id,
                "days": days,
                "reason": query[:200],
            },
        )
    m = _POLICY_PATTERN.search(query)
    if m:
        return DetectedIntent(
            tool="hr.policy_lookup",
            arguments={"policy_name": m.group(2).lower()},
        )
    m = _INCIDENT_OPEN_PATTERN.search(query)
    if m:
        # Infer priority from common phrasing; default normal.
        priority = "normal"
        if re.search(r"\b(urgent|critical|p0|p1)\b", query, re.IGNORECASE):
            priority = "critical"
        elif re.search(r"\b(high|important)\b", query, re.IGNORECASE):
            priority = "high"
        elif re.search(r"\b(low|minor)\b", query, re.IGNORECASE):
            priority = "low"
        return DetectedIntent(
            tool="itsm.incident_open",
            arguments={
                "title": query[:120],
                "description": query[:1000],
                "priority": priority,
                "reporter_employee_id": employee_id or "",
            },
        )
    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class AgentService:
    """Compose RAG + MCP. Stateless; safe to instantiate per request."""

    def __init__(
        self,
        *,
        rag: RagInferenceService,
        mcp: MCPClient | dict[str, MCPClient],
        audit_log: Any = None,
    ) -> None:
        self._rag = rag
        # Back-compat: accept a single MCPClient (wrap into {"hr": client})
        # OR a namespace→client dict for multi-server deployments. The
        # agent routes by ``intent.tool.split(".")[0]`` so every
        # enrolled namespace gets its own client with its own CB +
        # draft store + audit log context.
        if isinstance(mcp, MCPClient):
            self._clients: dict[str, MCPClient] = {"hr": mcp}
        else:
            self._clients = dict(mcp)
        # Optional AuditLog (documind_core.audit.AuditWriter).
        # When wired, agent-level scope denials produce
        # governance.audit_log rows so ops can see rejected attempts.
        self._audit = audit_log

    def _client_for(self, tool_name: str) -> MCPClient | None:
        """Route by namespace prefix: 'hr.leave_request' → self._clients['hr']."""
        namespace = tool_name.split(".", 1)[0] if "." in tool_name else tool_name
        return self._clients.get(namespace)

    async def _tool_required_scopes(self, tool_name: str) -> list[str]:
        """
        Look up the authoritative ``required_scopes`` list for a tool
        from ITS OWN MCP server's catalog (picked by namespace).
        Falls back to the ``<namespace>:write`` convention when the
        catalog is unreachable OR no client is registered for this
        namespace.

        Fallback semantics are conservative — we'd rather over-deny a
        read-only tool than under-deny a write tool.
        """
        client = self._client_for(tool_name)
        if client is None:
            return [required_role_for_tool(tool_name)]
        try:
            tools = await client.list_tools()
        except Exception as exc:  # noqa: BLE001 — MCP down is a valid state
            log.warning(
                "agent_tool_catalog_unreachable tool=%s err=%s — falling back to convention",
                tool_name, exc,
            )
            return [required_role_for_tool(tool_name)]
        tool = next((t for t in tools if t.get("name") == tool_name), None)
        if tool is None:
            return [required_role_for_tool(tool_name)]
        scopes = tool.get("required_scopes") or []
        if not scopes:
            return []
        return list(scopes)

    async def ask(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        request: AgentAskRequest,
        auth_token: str | None = None,
        roles: list[str] | None = None,
        auth_required: bool = False,
        idempotency_key: str | None = None,
    ) -> AgentAskResponse:
        # 1. Always ground the answer via RAG first.
        rag_req = AskRequest(
            query=request.query,
            top_k=request.top_k,
            model=request.model,
            strategy=request.strategy,
        )
        base = await self._rag.ask(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            request=rag_req,
            include_debug=False,
        )

        # 2. Intent detection
        intent = _detect_intent(request.query, request.employee_id)
        if intent is None:
            return AgentAskResponse(**base.model_dump(), action=None, intent="answer")

        if not request.allow_actions:
            log.info(
                "agent_action_declined tool=%s reason=allow_actions_false corr=%s",
                intent.tool, correlation_id,
            )
            record_agent_denial(reason="allow_actions_false", tool=intent.tool)
            return AgentAskResponse(
                **base.model_dump(), action=None, intent="action_declined",
            )

        # 2b. Scope pre-check — if auth is enforced and the caller
        # doesn't have the role this tool requires, short-circuit before
        # the MCP round-trip. The user still gets the grounded RAG
        # answer plus a structured denial; we don't waste the MCP call
        # OR expose tool invocation attempts to audit as "failed" when
        # the policy already forbade them.
        #
        # Required scopes come from MCPClient.list_tools() — the MCP
        # server's own tool catalog, which is the source of truth. If
        # that call fails (MCP unreachable, CB open), we fall back to
        # the ``<namespace>:write`` convention. Conservative: the
        # fallback may over-deny a read-only tool, but never under-denies
        # a write tool.
        if auth_required:
            required_scopes = await self._tool_required_scopes(intent.tool)
            have = set(roles or [])
            if required_scopes and set(required_scopes).isdisjoint(have):
                log.info(
                    "agent_action_denied_scope tool=%s required=%s have=%s corr=%s",
                    intent.tool, sorted(required_scopes), sorted(have), correlation_id,
                )
                record_agent_denial(reason="scope", tool=intent.tool)
                # Audit the rejection — invisible denials are the kind
                # of thing governance reviews ask for after an
                # incident. Hash-chained onto the existing per-tenant
                # chain (the AuditWriter handles that).
                if self._audit is not None and tenant_id:
                    await self._audit.write(
                        tenant_id=tenant_id,
                        action="agent.scope_denied",
                        resource_type="agent_action",
                        details={
                            "tool": intent.tool,
                            "required": sorted(required_scopes),
                            "have": sorted(have),
                            "query_preview": request.query[:120],
                        },
                        correlation_id=correlation_id,
                    )
                denied = AgentAction(
                    tool=intent.tool,
                    ok=False,
                    error={
                        "code": "INSUFFICIENT_SCOPE",
                        "required": sorted(required_scopes),
                        "have": sorted(have),
                        "tool": intent.tool,
                    },
                )
                return AgentAskResponse(
                    **base.model_dump(),
                    action=denied,
                    intent="action_denied_scope",
                )

        # 3. Invoke MCP — route by namespace
        client = self._client_for(intent.tool)
        if client is None:
            log.warning(
                "agent_no_client_for_namespace tool=%s corr=%s",
                intent.tool, correlation_id,
            )
            unavailable = AgentAction(
                tool=intent.tool,
                ok=False,
                error={
                    "code": "NO_SERVER_FOR_NAMESPACE",
                    "namespace": intent.tool.split(".", 1)[0],
                    "tool": intent.tool,
                    "message": "No MCP server configured for this namespace in this deployment",
                },
            )
            return AgentAskResponse(
                **base.model_dump(),
                action=unavailable,
                intent="action_unavailable",
            )

        log.info(
            "agent_invoking_tool tool=%s tenant=%s corr=%s",
            intent.tool, tenant_id, correlation_id,
        )
        # Forward the caller-supplied idempotency key (if any) so MCP's
        # cache dedupes retries end-to-end. Without this, the MCPClient
        # would generate a fresh uuid4 key on every call — making a
        # client-retry on network hiccups create two tickets.
        result: ToolResult = await client.call_tool(
            intent.tool,
            intent.arguments,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            auth_token=auth_token,
            idempotency_key=idempotency_key,
        )
        action = AgentAction(
            tool=intent.tool,
            ok=result.ok,
            result=result.data,
            error=result.error,
            degraded=result.degraded,
            draft_id=result.draft_id,
            idempotent_replay=result.idempotent_replay,
        )
        return AgentAskResponse(**base.model_dump(), action=action, intent="action")
