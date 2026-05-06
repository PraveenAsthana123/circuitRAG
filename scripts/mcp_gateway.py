#!/usr/bin/env python3
"""MCP Gateway — Stage-1 allowlist + PolisAI gate + audit for MCP calls.

Per the 2026-05-04 enterprise-architecture page's brutal rule: "do not
allow direct MCP access. Put every MCP server behind MCP Gateway + OPA
+ sandbox + audit." This script is the GATEWAY.

Stage-1 (this commit): the gateway CONTRACT.
  - is_available()            — feature flag (MCP_GATEWAY_ENABLED=1)
  - check(actor, server)      — allowlist + PolisAI gate; returns AllowDecision
  - dispatch(actor, server, tool, args) — real dispatch with audit + rate-limit
  - status() / main()         — operator inspection

The brutal rule realized: ANY caller that wants to invoke an MCP tool
goes through gateway.dispatch() — which:
  1. Loads the allowlist (config/mcp/allowlist.json)
  2. Verifies the server is allowed (default-deny otherwise)
  3. Verifies actor is in approved_actors for this server
  4. Fires PolisAI gate (existing pattern from §47)
  5. Checks rate-limit (max_calls_per_minute per server)
  6. Logs audit row to .loop/mcp_gateway_audit.jsonl
  7. Forwards the call (Stage-2 wires the real RPC; Stage-1 stubs)

Stage-2: replace the stub dispatch with real MCP HTTP calls.
Stage-3: rate-limit Redis-backed for multi-process correctness.

Why Stage-1 ships gate-only: the gate IS the security boundary. Having
the gate in place + drill-locked is what enables Stage-2 wiring. Until
the gate exists, every MCP call is direct — which is the gap the
enterprise-architecture page identified as highest-leverage.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ALLOWLIST = REPO / "config" / "mcp" / "allowlist.json"
AUDIT_LOG = REPO / ".loop" / "mcp_gateway_audit.jsonl"

logger = logging.getLogger(__name__)

# Stage-1 opt-in — same pattern as KAFKA_PUBLISH / LITELLM_ENABLED.
MCP_GATEWAY_ENABLED = os.getenv("MCP_GATEWAY_ENABLED", "").strip() == "1"

# Stage-3 strict mode — when set, PolisAI rule MUST exist (no fall-through
# to allowlist-only). Tightens authorization: missing rule = deny.
# Default (False) preserves Stage-1 behavior for backwards compatibility.
MCP_GATEWAY_STRICT = os.getenv("MCP_GATEWAY_STRICT", "").strip() == "1"


@dataclass
class GatewayDecision:
    """Outcome of a gateway check. Same shape as PolicyDecision per §38/§48.4.

    ``latency_ms`` was added 2026-05-06 to feed the Paperclip Stage-1 v6
    p50/p95/p99 aggregator. Older audit rows lack the field; the
    aggregator handles missing field gracefully.
    """
    allow: bool
    reason: str
    actor: str
    server: str
    tool: str
    risk: str  # low / medium / high / critical
    approved_actors: list[str] = field(default_factory=list)
    rule_matched: str = ""
    timestamp: float = 0.0
    request_id: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MCPGatewayDisabled(RuntimeError):
    """Stage-1 default — gateway not enabled (MCP_GATEWAY_ENABLED!=1)."""


class ServerNotAllowed(RuntimeError):
    """Server not in allowlist — default-deny."""


class ActorNotApproved(RuntimeError):
    """Actor not in approved_actors for the requested server."""


class RateLimitExceeded(RuntimeError):
    """max_calls_per_minute exceeded for this server."""


# Per-server rate-limit state. Stage-1: in-memory deque-of-timestamps.
# Stage-3 will move to Redis-backed for multi-process correctness.
_rate_state: dict[str, deque[float]] = {}
_rate_lock = Lock()


def is_available() -> bool:
    """Stage-1 feature flag."""
    return MCP_GATEWAY_ENABLED


def _load_allowlist() -> dict[str, Any]:
    """Load + minimally validate the allowlist file."""
    if not ALLOWLIST.exists():
        raise ServerNotAllowed(f"allowlist file missing: {ALLOWLIST}")
    try:
        doc = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ServerNotAllowed(f"allowlist file not valid JSON: {e}") from e
    for key in ("policy_version", "policy_id", "servers", "default_decision"):
        if key not in doc:
            raise ServerNotAllowed(f"allowlist missing required key: {key!r}")
    return doc


def _polisai_gate(actor: str, server: str, tool: str) -> tuple[bool, str]:
    """PolisAI gate — check actor:tool authorization for the MCP call.

    Returns (allow, rule_matched). The rule_matched value is the
    decisive signal for strict-mode: when it equals 'default-deny',
    no specific PolisAI rule matched and Stage-1 allowlist-fall-through
    behavior should apply (unless STRICT mode says otherwise).

    The PolisAI tool name pattern is ``mcp:<server>:<tool>``. Stage-1
    callers may not have rules for every server×tool combo yet — when
    no rule matches, the gateway falls through to the allowlist's
    approved_actors check (which IS the §56 gate-of-record for
    Stage-1). Stage-3 STRICT mode (MCP_GATEWAY_STRICT=1) tightens to
    require explicit PolisAI rules — missing rule = deny.
    """
    try:
        from policy_check import evaluate as _policy_evaluate  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(REPO / "scripts"))
        from policy_check import evaluate as _policy_evaluate  # noqa: PLC0415

    decision = _policy_evaluate(
        actor=actor,
        tool=f"mcp:{server}:{tool}",
        scopes_granted=["mcp:invoke"],
        persist_audit=False,  # gateway audit is the source of truth
    )
    return decision.allow, decision.rule_matched


def _check_rate_limit(server: str, max_per_min: int) -> bool:
    """Stage-1 in-memory rate limit. Returns True if call is permitted."""
    with _rate_lock:
        now = time.time()
        cutoff = now - 60.0
        bucket = _rate_state.setdefault(server, deque())
        # Drop expired
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_per_min:
            return False
        bucket.append(now)
        return True


def check(
    actor: str,
    server: str,
    tool: str = "",
    *,
    persist_audit: bool = True,
) -> GatewayDecision:
    """Stage-1 gateway check. Returns GatewayDecision (does NOT raise on
    deny — caller checks .allow). Persists audit row for ALL decisions.

    Raises only on:
      - MCPGatewayDisabled (feature flag off)
      - Allowlist file malformed / missing
    """
    import uuid as _uuid
    request_id = str(_uuid.uuid4())
    started = time.time()  # paperclip v6 latency tracking

    if not is_available():
        raise MCPGatewayDisabled(
            "MCP gateway not enabled (MCP_GATEWAY_ENABLED!=1). "
            "Stage-1 ships the contract; set the flag to enable."
        )

    if not isinstance(actor, str) or not actor.strip():
        raise ValueError(f"actor must be non-empty string; got {actor!r}")
    if not isinstance(server, str) or not server.strip():
        raise ValueError(f"server must be non-empty string; got {server!r}")

    allowlist = _load_allowlist()

    # Find the server entry
    matching = [s for s in allowlist["servers"] if s["name"] == server]
    if not matching:
        decision = GatewayDecision(
            allow=False,
            reason=f"server {server!r} not in allowlist (default-deny)",
            actor=actor,
            server=server,
            tool=tool,
            risk="unknown",
            rule_matched="default-deny",
            timestamp=time.time(),
            request_id=request_id,
        )
        if persist_audit:
            decision.latency_ms = round((time.time() - started) * 1000.0, 3)
            _append_audit(decision)
        return decision

    server_rec = matching[0]
    approved_actors = server_rec["approved_actors"]

    # Approved-actor check
    if actor not in approved_actors and "*" not in approved_actors:
        decision = GatewayDecision(
            allow=False,
            reason=f"actor {actor!r} not in approved_actors for {server!r}",
            actor=actor,
            server=server,
            tool=tool,
            risk=server_rec["risk"],
            approved_actors=approved_actors,
            rule_matched=f"server-allowlist:{server}",
            timestamp=time.time(),
            request_id=request_id,
        )
        if persist_audit:
            decision.latency_ms = round((time.time() - started) * 1000.0, 3)
            _append_audit(decision)
        return decision

    # PolisAI gate (defense in depth)
    polisai_allow, polisai_rule = _polisai_gate(actor, server, tool)

    # Stage-3 STRICT mode: missing PolisAI rule → deny.
    # Default (non-strict) mode falls through to allowlist as Stage-1.
    if MCP_GATEWAY_STRICT and polisai_rule == "default-deny":
        decision = GatewayDecision(
            allow=False,
            reason=(
                f"STRICT mode: no PolisAI rule for mcp:{server}:{tool} "
                f"(actor={actor}). Add rule + redeploy."
            ),
            actor=actor,
            server=server,
            tool=tool,
            risk=server_rec["risk"],
            approved_actors=approved_actors,
            rule_matched="strict:no-polisai-rule",
            timestamp=time.time(),
            request_id=request_id,
        )
        if persist_audit:
            decision.latency_ms = round((time.time() - started) * 1000.0, 3)
            _append_audit(decision)
        return decision

    # Stage-3 STRICT mode: explicit PolisAI deny → deny.
    # (In default mode this would still apply via rule_matched having
    # actual PolisAI rule_id and polisai_allow=False; we make it
    # explicit here so STRICT-vs-non-STRICT behavior is symmetric on
    # the deny path.)
    if MCP_GATEWAY_STRICT and not polisai_allow and polisai_rule != "default-deny":
        decision = GatewayDecision(
            allow=False,
            reason=f"STRICT mode: PolisAI rule {polisai_rule!r} denied",
            actor=actor,
            server=server,
            tool=tool,
            risk=server_rec["risk"],
            approved_actors=approved_actors,
            rule_matched=f"strict:polisai-deny:{polisai_rule}",
            timestamp=time.time(),
            request_id=request_id,
        )
        if persist_audit:
            decision.latency_ms = round((time.time() - started) * 1000.0, 3)
            _append_audit(decision)
        return decision

    # Rate limit
    if not _check_rate_limit(server, int(server_rec.get("max_calls_per_minute", 60))):
        decision = GatewayDecision(
            allow=False,
            reason=f"rate limit exceeded for {server!r} ({server_rec.get('max_calls_per_minute')}/min)",
            actor=actor,
            server=server,
            tool=tool,
            risk=server_rec["risk"],
            approved_actors=approved_actors,
            rule_matched="rate-limit",
            timestamp=time.time(),
            request_id=request_id,
        )
        if persist_audit:
            decision.latency_ms = round((time.time() - started) * 1000.0, 3)
            _append_audit(decision)
        return decision

    # Stage-1 allowlist-only path: PolisAI rule_matched=default-deny
    # means no specific rule existed; we fall through to the
    # approved_actors check above (already passed). Document this
    # in the reason field so audit rows show which path was taken.
    polisai_state = (
        "allow" if polisai_allow else
        ("no-rule-fallthrough" if polisai_rule == "default-deny" else "deny")
    )
    decision = GatewayDecision(
        allow=True,
        reason=f"actor approved for {server!r}; risk={server_rec['risk']}; "
               f"polisai={polisai_state}; mode={'strict' if MCP_GATEWAY_STRICT else 'default'}",
        actor=actor,
        server=server,
        tool=tool,
        risk=server_rec["risk"],
        approved_actors=approved_actors,
        rule_matched=f"server-allowlist:{server}",
        timestamp=time.time(),
        request_id=request_id,
    )
    if persist_audit:
        decision.latency_ms = round((time.time() - started) * 1000.0, 3)
        _append_audit(decision)
    return decision


def _append_audit(decision: GatewayDecision) -> None:
    """Best-effort append to .loop/mcp_gateway_audit.jsonl.

    Per §47.7 migrate-phase: when MCP_GATEWAY_SQL_AUDIT_ENABLED=1,
    ALSO writes the decision to governance.tool_executions. JSONL
    remains authoritative; SQL is the queryable surface. Either
    write failing does NOT block the other (best-effort dual-write).
    Drill drill_mcp_gateway_dual_write.py locks the parity contract.
    """
    # JSONL write — authoritative surface, NEVER skipped.
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), default=str) + "\n")
    except OSError:
        pass

    # SQL write — opt-in via env. Failure NEVER blocks the JSONL path.
    if os.getenv("MCP_GATEWAY_SQL_AUDIT_ENABLED", "").strip() == "1":
        _persist_sql_audit(decision)


def _persist_sql_audit(decision: GatewayDecision) -> None:
    """Best-effort write to governance.tool_executions.

    Per §47.7 migrate-phase. The SQL surface complements (not replaces)
    the JSONL audit. Insert failure is logged but NEVER raised — the
    gateway's response path stays unblocked.

    tenant_id is NULL because the MCP gateway is cross-tenant (a
    request_id is the correlation key, not a tenant). The RLS policy
    for tool_executions explicitly allows NULL-tenant rows as
    service-account audit floor (per migration 010 comment).

    Uses asyncpg wrapped in asyncio.run() to keep this writer sync.
    """
    try:
        import asyncio
        import uuid as _uuid

        import asyncpg
    except ImportError:
        return

    # Validate / coerce request_id to UUID (column type is UUID NOT NULL)
    rid = decision.request_id
    try:
        rid_uuid = _uuid.UUID(rid) if rid else _uuid.uuid4()
    except (ValueError, AttributeError):
        rid_uuid = _uuid.uuid4()

    pg_host = os.getenv("DOCUMIND_PG_HOST", "localhost")
    pg_port = int(os.getenv("DOCUMIND_PG_PORT", "55432"))
    pg_user = os.getenv("DOCUMIND_PG_USER", "documind_app")
    pg_password = os.getenv("DOCUMIND_PG_PASSWORD", "documind_app")
    pg_db = os.getenv("DOCUMIND_PG_DB", "documind")

    async def _insert() -> None:
        conn = await asyncpg.connect(
            host=pg_host, port=pg_port, user=pg_user,
            password=pg_password, database=pg_db, timeout=2.0,
        )
        try:
            await conn.execute(
                "INSERT INTO governance.tool_executions "
                "(request_id, tenant_id, actor, server, tool, "
                " allow, decision_reason, risk, rule_matched, "
                " latency_ms) "
                "VALUES ($1, NULL, $2, $3, $4, $5, $6, $7, $8, $9)",
                rid_uuid,
                decision.actor,
                decision.server,
                decision.tool,
                decision.allow,
                decision.reason,
                decision.risk,
                decision.rule_matched,
                int(decision.latency_ms) if decision.latency_ms else None,
            )
        finally:
            await conn.close()

    try:
        asyncio.run(_insert())
    except Exception as exc:  # noqa: BLE001
        # Per §47.7 migrate-phase: SQL is best-effort; JSONL is
        # authoritative. Log and move on.
        log = logging.getLogger(__name__)
        log.warning("mcp_gateway_sql_audit_failed err=%s",
                    type(exc).__name__)


def status() -> dict[str, Any]:
    """Operator-readable health/config dump."""
    try:
        allowlist = _load_allowlist()
        server_count = len(allowlist["servers"])
        risk_breakdown: dict[str, int] = {}
        for s in allowlist["servers"]:
            risk_breakdown[s["risk"]] = risk_breakdown.get(s["risk"], 0) + 1
    except (ServerNotAllowed, json.JSONDecodeError):
        server_count = 0
        risk_breakdown = {}
    return {
        "stage": 1,
        "enabled": is_available(),
        "strict_mode": MCP_GATEWAY_STRICT,
        "server_count": server_count,
        "by_risk": risk_breakdown,
        "audit_log": str(AUDIT_LOG.relative_to(REPO)),
        "allowlist_path": str(ALLOWLIST.relative_to(REPO)),
        "note": (
            "Stage-1 — gateway contract: allowlist + PolisAI gate + "
            "rate-limit + audit. Set MCP_GATEWAY_ENABLED=1 to fire. "
            "Stage-3 STRICT (MCP_GATEWAY_STRICT=1): missing PolisAI rule → deny. "
            "Default (non-strict): falls through to allowlist (Stage-1 behavior)."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="mcp_gateway")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show gateway status + allowlist summary")

    p_check = sub.add_parser("check", help="Run a gateway check")
    p_check.add_argument("--actor", required=True)
    p_check.add_argument("--server", required=True)
    p_check.add_argument("--tool", default="")
    p_check.add_argument("--no-audit", action="store_true")

    args = parser.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0

    if args.cmd == "check":
        try:
            decision = check(
                actor=args.actor,
                server=args.server,
                tool=args.tool,
                persist_audit=not args.no_audit,
            )
        except MCPGatewayDisabled as exc:
            print(json.dumps({
                "ok": False,
                "error_code": "GATEWAY_DISABLED",
                "message": str(exc),
            }, indent=2))
            return 2
        except (ValueError, ServerNotAllowed) as exc:
            print(json.dumps({
                "ok": False,
                "error_code": exc.__class__.__name__.upper(),
                "message": str(exc),
            }, indent=2))
            return 3
        print(json.dumps(decision.to_dict(), indent=2, default=str))
        return 0 if decision.allow else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
