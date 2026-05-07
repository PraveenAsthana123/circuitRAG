#!/usr/bin/env python3
"""OpenClaw Stage-1 — heavy-autonomy A2A (agent-to-agent) coordinator.

Per CLAUDE.md §47 (11-layer architecture, Layer 11) + ADR-012.
OpenClaw is the OPPOSITE of Paperclip: where Paperclip is read-only
sandbox, OpenClaw is autonomous delegation across services.

Both go through PolisAI first.

Stage-1 contract — exactly what's locked here:

  - Agent registry (read-only) — capabilities + scopes per agent
  - Dispatch CONTRACT (no actual dispatch; just the envelope shape)
  - Every dispatch attempt goes through PolisAI first
  - Default-deny posture — unknown actor / target / capability rejected
  - Audit row per dispatch attempt (allow + deny) per §38 / §48.4
  - NO actual execution of remote agent calls (Stage-2 wires those)

Stage-2 (next iteration) wires:
  - Real RPC dispatch to target agents (gRPC or MCP tool calls)
  - Per-call timeout + retry with exponential backoff
  - Circuit breaker per (source_agent, target_agent) pair
  - Cost ceiling per dispatch chain

Stage-3 wires the full multi-agent task graph with:
  - Parallel dispatch fan-out
  - Result aggregation + reduce
  - Human-in-loop escalation on conflict

Why Stage-1 is just contract + drill: A2A delegation that ships before
the policy gate is wired is exactly the "Excessive Agency" risk
called out in OWASP A15. Without PolisAI on the dispatch path, an
agent could delegate to any other agent regardless of scope. Stage-1
ships the GATE first; Stage-2 ships the EXECUTION on top.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AUDIT_LOG = REPO / ".loop" / "openclaw_audit.jsonl"


# ---------------------------------------------------------------------------
# Stage-1 agent registry — STATIC DICT.
# Stage-2 swaps this to the live agent_registry service. The registry
# CONTRACT (capability + required_scope per agent) stays.
# ---------------------------------------------------------------------------
AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "council:author": {
        "capabilities": ["propose_fix", "generate_diff"],
        "required_scope": "delegate:council:author",
        "endpoint": "local://scripts/local_council.py",
        "stage": 1,
    },
    "council:reviewer": {
        "capabilities": ["critique_proposal"],
        "required_scope": "delegate:council:reviewer",
        "endpoint": "local://scripts/local_council.py",
        "stage": 1,
    },
    "council:advisor": {
        "capabilities": ["synthesize_alternative"],
        "required_scope": "delegate:council:advisor",
        "endpoint": "local://scripts/local_council.py",
        "stage": 1,
    },
    "council:researcher": {
        "capabilities": ["gather_context", "grep_codebase"],
        "required_scope": "delegate:council:researcher",
        "endpoint": "local://scripts/local_council.py",
        "stage": 1,
    },
    "paperclip:manager": {
        "capabilities": ["read_snapshot"],
        "required_scope": "delegate:paperclip:manager",
        "endpoint": "local://scripts/paperclip_manager.py",
        "stage": 1,
    },
    "operator:human": {
        "capabilities": ["approve", "reject", "escalate"],
        "required_scope": "delegate:operator:human",
        "endpoint": "human-in-loop://hitl",
        "stage": 1,
    },
}


@dataclass
class DispatchEnvelope:
    """The A2A message shape per §38 audit-row schema + §47 architecture."""
    dispatch_id: str
    timestamp: float
    requesting_agent: str
    target_agent: str
    capability: str
    correlation_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    scopes_granted: list[str] = field(default_factory=list)


@dataclass
class DispatchDecision:
    """Outcome of the PolisAI gate + registry check."""
    allow: bool
    reason: str
    rule_matched: str
    requesting_agent: str
    target_agent: str
    capability: str
    scopes_required: list[str] = field(default_factory=list)
    scopes_granted: list[str] = field(default_factory=list)
    missing_scopes: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    dispatch_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenClawError(RuntimeError):
    """Base class for OpenClaw errors. Subclass for specific causes."""


class UnknownAgentError(OpenClawError):
    """Target or requesting agent not in the registry."""


class CapabilityNotSupportedError(OpenClawError):
    """Target agent does not list the requested capability."""


def _polisai_gate(
    requesting_agent: str,
    target_agent: str,
    capability: str,
    scopes_granted: list[str],
) -> DispatchDecision:
    """Run the PolisAI gate for a dispatch attempt.

    The dispatch tool is named ``a2a:dispatch:<target>``. PolisAI
    rules either allow that (actor, tool) pair OR default-deny.

    The caller is the *requesting* agent; the *target* is in the
    tool name. This is the right boundary: a malicious actor with
    research:author scopes shouldn't be able to delegate to
    operator:human just because the target also has a rule.
    """
    try:
        from policy_check import evaluate as _policy_evaluate
    except ImportError:
        sys.path.insert(0, str(REPO / "scripts"))
        from policy_check import evaluate as _policy_evaluate

    tool = f"a2a:dispatch:{target_agent}"
    decision = _policy_evaluate(
        actor=requesting_agent,
        tool=tool,
        scopes_granted=scopes_granted,
        persist_audit=True,
    )
    return DispatchDecision(
        allow=decision.allow,
        reason=decision.reason,
        rule_matched=decision.rule_matched,
        requesting_agent=requesting_agent,
        target_agent=target_agent,
        capability=capability,
        scopes_required=decision.scope_required,
        scopes_granted=decision.scope_granted,
        missing_scopes=decision.missing_scopes,
        timestamp=decision.timestamp,
        dispatch_id="",
    )


def evaluate_dispatch(
    *,
    requesting_agent: str,
    target_agent: str,
    capability: str,
    scopes_granted: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> tuple[DispatchDecision, DispatchEnvelope | None]:
    """The Stage-1 dispatch gate. Returns (decision, envelope).

    On allow: envelope is the constructed A2A message Stage-2 would
    send. Stage-1 does NOT actually send it — that's the contract
    boundary. The envelope is returned so the caller can choose to
    persist it, hand to Stage-2 transport, etc.

    On deny: envelope is None. The decision carries the rule_matched +
    reason so the caller can surface an actionable error.

    Raises OpenClawError subclasses for malformed-input cases:
      - Unknown requesting_agent / target_agent → UnknownAgentError
      - Capability not in target's registry entry → CapabilityNotSupportedError
    """
    if requesting_agent not in AGENT_REGISTRY:
        raise UnknownAgentError(
            f"requesting_agent {requesting_agent!r} not in registry; "
            f"known: {sorted(AGENT_REGISTRY.keys())}"
        )
    if target_agent not in AGENT_REGISTRY:
        raise UnknownAgentError(
            f"target_agent {target_agent!r} not in registry; "
            f"known: {sorted(AGENT_REGISTRY.keys())}"
        )

    target_info = AGENT_REGISTRY[target_agent]
    if capability not in target_info["capabilities"]:
        raise CapabilityNotSupportedError(
            f"target {target_agent!r} does not support capability "
            f"{capability!r}; supports: {target_info['capabilities']}"
        )

    granted = list(scopes_granted or [])
    decision = _polisai_gate(
        requesting_agent=requesting_agent,
        target_agent=target_agent,
        capability=capability,
        scopes_granted=granted,
    )
    decision.dispatch_id = str(uuid.uuid4())
    envelope: DispatchEnvelope | None = None
    if decision.allow:
        envelope = DispatchEnvelope(
            dispatch_id=decision.dispatch_id,
            timestamp=time.time(),
            requesting_agent=requesting_agent,
            target_agent=target_agent,
            capability=capability,
            correlation_id=correlation_id or str(uuid.uuid4()),
            payload=dict(payload or {}),
            scopes_granted=granted,
        )

    _append_audit(decision, envelope)
    # Stage-2 fan-out to Kafka observability bus per §47 Layer 8.
    # Fail-open: publish failure never blocks the dispatch return.
    try:
        from event_publisher import publish_openclaw_dispatch  # noqa: PLC0415
        publish_openclaw_dispatch(
            dispatch_decision=decision.to_dict(),
            correlation_id=envelope.correlation_id if envelope else None,
        )
    except Exception:  # noqa: BLE001 — fan-out is best-effort
        pass
    return decision, envelope


def _append_audit(decision: DispatchDecision, envelope: DispatchEnvelope | None) -> None:
    """Append every dispatch decision (allow + deny) to .loop/openclaw_audit.jsonl."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        row: dict[str, Any] = {
            "type": "dispatch",
            "decision": decision.to_dict(),
            "envelope": asdict(envelope) if envelope else None,
        }
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Stage-2 dispatch — gate + envelope + transport via MCP gateway.
# ---------------------------------------------------------------------------


@dataclass
class DispatchResult:
    """Outcome of a Stage-2 dispatch — wraps decision + transport result.

    ok=True iff: (1) PolisAI gated, (2) envelope built, (3) transport
    succeeded. Any earlier rejection sets ok=False; transport_error
    is None on success or before transport was attempted.
    """
    ok: bool
    decision: DispatchDecision
    envelope: DispatchEnvelope | None = None
    transport_error: str | None = None
    response_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision"] = self.decision.to_dict()
        if self.envelope is not None:
            d["envelope"] = asdict(self.envelope)
        return d


def dispatch(
    *,
    requesting_agent: str,
    target_agent: str,
    capability: str,
    scopes_granted: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> DispatchResult:
    """Stage-2 dispatch — evaluate + transport.

    Flow:
      1. Run evaluate_dispatch() — same Stage-1 gate path
      2. If allow=False → return DispatchResult(ok=False, ...)
      3. Map target_agent's endpoint to an MCP server name
         (registry already documents this via 'endpoint' field)
      4. Route through mcp_gateway.check() — defense in depth (the
         gateway also fires PolisAI gate; double-gate is intentional
         here because OpenClaw's gate authorizes A2A delegation
         while the MCP gateway authorizes the underlying MCP call)
      5. On gateway allow → log dispatch event; Stage-2 stops here
         (real RPC send is Stage-3 — needs each agent to be a
         server, which is a bigger architectural step)
      6. Persist a synthetic audit row indicating Stage-2 transport
         attempt outcome

    The 'transport' is currently a no-op (Stage-2 is contract +
    audit). Stage-3 implements the real HTTP/gRPC send. Drill locks:
    every dispatch() call goes through evaluate_dispatch FIRST,
    transport only happens on allow, audit row records BOTH stages.
    """
    decision, envelope = evaluate_dispatch(
        requesting_agent=requesting_agent,
        target_agent=target_agent,
        capability=capability,
        scopes_granted=scopes_granted,
        payload=payload,
        correlation_id=correlation_id,
    )

    if not decision.allow or envelope is None:
        return DispatchResult(
            ok=False,
            decision=decision,
            envelope=None,
            transport_error=f"openclaw gate denied: {decision.reason}",
        )

    # MCP gateway check — when MCP_GATEWAY_ENABLED, route through it.
    # The target_agent's registry endpoint indicates the MCP server.
    target_info = AGENT_REGISTRY[target_agent]
    endpoint = target_info["endpoint"]
    transport_error: str | None = None

    # Parse server name from endpoint. Format examples:
    #   "local://scripts/local_council.py" → no MCP server
    #   "human-in-loop://hitl"             → no MCP server
    #   "mcp://research"                    → research MCP server
    if endpoint.startswith("mcp://"):
        server_name = endpoint[len("mcp://"):]
        try:
            sys.path.insert(0, str(REPO / "scripts"))
            from mcp_gateway import (  # noqa: PLC0415
                MCPGatewayDisabled,
            )
            from mcp_gateway import (
                check as _gateway_check,
            )
            try:
                gate = _gateway_check(
                    actor=requesting_agent,
                    server=server_name,
                    tool=capability,
                    persist_audit=True,
                )
                if not gate.allow:
                    transport_error = (
                        f"mcp gateway denied transport to {server_name}: "
                        f"{gate.reason}"
                    )
            except MCPGatewayDisabled:
                # Gateway not enabled — Stage-2 records dispatch but
                # actual transport is a no-op. That's the documented
                # opt-in behavior (matches LiteLLM Stage-2 pattern).
                transport_error = "mcp_gateway_disabled (Stage-2 no-op)"
        except ImportError:
            transport_error = "mcp_gateway_unavailable"

    # Stage-3 stub: actual RPC send would go here when agents are
    # exposed as servers. For Stage-2, we record the dispatch as
    # successful (gate passed, envelope built) — the transport step
    # is a no-op.
    if transport_error and "denied" in transport_error.lower():
        return DispatchResult(
            ok=False,
            decision=decision,
            envelope=envelope,
            transport_error=transport_error,
        )

    return DispatchResult(
        ok=True,
        decision=decision,
        envelope=envelope,
        transport_error=transport_error,  # may carry "Stage-2 no-op" note
        response_data={"stage": 2, "transport_outcome": "no-op"},
    )


# ---------------------------------------------------------------------------
# Inspection helpers — read-only operator surface.
# ---------------------------------------------------------------------------

def list_agents() -> dict[str, Any]:
    """Operator-readable agent registry inspection. Read-only."""
    return {
        "stage": 1,
        "agent_count": len(AGENT_REGISTRY),
        "agents": {
            name: {
                "capabilities": info["capabilities"],
                "required_scope": info["required_scope"],
                "endpoint": info["endpoint"],
            }
            for name, info in AGENT_REGISTRY.items()
        },
    }


def recent_dispatches(limit: int = 10) -> list[dict[str, Any]]:
    """Read recent dispatch decisions from the audit log."""
    if not AUDIT_LOG.exists():
        return []
    rows = []
    with AUDIT_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]  # newest first


# ---------------------------------------------------------------------------
# CLI — operator inspection + drill harness.
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="openclaw_coordinator",
        description="Stage-1 A2A coordinator — gate + envelope contract only.",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("agents", help="List the agent registry")
    sub.add_parser("dispatches", help="Show recent dispatch decisions")

    p_eval = sub.add_parser("dispatch", help="Evaluate a dispatch attempt")
    p_eval.add_argument("--from", dest="requesting_agent", required=True)
    p_eval.add_argument("--to", dest="target_agent", required=True)
    p_eval.add_argument("--capability", required=True)
    p_eval.add_argument("--scopes", default="", help="comma-separated")
    p_eval.add_argument("--payload", default="{}", help="JSON payload")

    args = parser.parse_args()

    if args.cmd == "agents":
        print(json.dumps(list_agents(), indent=2))
        return 0

    if args.cmd == "dispatches":
        print(json.dumps(recent_dispatches(20), indent=2, default=str))
        return 0

    if args.cmd == "dispatch":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(json.dumps({
                "ok": False,
                "error_code": "INVALID_PAYLOAD",
                "message": str(exc),
            }))
            return 3
        scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
        try:
            decision, envelope = evaluate_dispatch(
                requesting_agent=args.requesting_agent,
                target_agent=args.target_agent,
                capability=args.capability,
                scopes_granted=scopes,
                payload=payload,
            )
        except OpenClawError as exc:
            print(json.dumps({
                "ok": False,
                "error_code": exc.__class__.__name__,
                "message": str(exc),
            }))
            return 3
        print(json.dumps({
            "decision": decision.to_dict(),
            "envelope": asdict(envelope) if envelope else None,
        }, indent=2, default=str))
        return 0 if decision.allow else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
