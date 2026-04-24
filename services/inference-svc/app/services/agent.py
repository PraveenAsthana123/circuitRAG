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
        mcp: MCPClient,
        audit_log: Any = None,
    ) -> None:
        self._rag = rag
        self._mcp = mcp
        # Optional AuditLog (documind_core.audit.AuditWriter).
        # When wired, agent-level scope denials produce
        # governance.audit_log rows so ops can see rejected attempts.
        self._audit = audit_log

    async def _tool_required_scopes(self, tool_name: str) -> list[str]:
        """
        Look up the authoritative ``required_scopes`` list for a tool
        from the MCP server's own catalog. Falls back to the
        ``<namespace>:write`` convention when the catalog is unreachable.

        Fallback semantics are conservative — we'd rather over-deny a
        read-only tool than under-deny a write tool. When MCP recovers,
        the next call uses the real catalog.
        """
        try:
            tools = await self._mcp.list_tools()
        except Exception as exc:  # noqa: BLE001 — MCP down is a valid state
            log.warning(
                "agent_tool_catalog_unreachable tool=%s err=%s — falling back to convention",
                tool_name, exc,
            )
            return [required_role_for_tool(tool_name)]
        tool = next((t for t in tools if t.get("name") == tool_name), None)
        if tool is None:
            # Unknown tool — fallback to convention so we at least gate
            # the call at *some* scope before MCP's 404.
            return [required_role_for_tool(tool_name)]
        scopes = tool.get("required_scopes") or []
        if not scopes:
            # Tool explicitly declares no required scopes — allow any
            # authenticated caller. Unusual but legal.
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

        # 3. Invoke MCP
        log.info(
            "agent_invoking_tool tool=%s tenant=%s corr=%s",
            intent.tool, tenant_id, correlation_id,
        )
        result: ToolResult = await self._mcp.call_tool(
            intent.tool,
            intent.arguments,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            auth_token=auth_token,
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
