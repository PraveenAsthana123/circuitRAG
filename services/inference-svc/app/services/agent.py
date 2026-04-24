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

    def __init__(self, *, rag: RagInferenceService, mcp: MCPClient) -> None:
        self._rag = rag
        self._mcp = mcp

    async def ask(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        request: AgentAskRequest,
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
