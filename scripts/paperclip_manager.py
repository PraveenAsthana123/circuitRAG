#!/usr/bin/env python3
"""Paperclip Stage-1 — read-only manager-layer aggregator.

Per CLAUDE.md §47 (orchestration architecture) + ADR-012
(Paperclip = manager UX above MCP/council substrate). Stage-1 is
**read-only by contract**: subscribes to existing surfaces, never
writes, never dispatches.

The architecture:

  Policy (OPA)  →  Manager (Paperclip)  →  Workers (council)  →  External
                       ↑
                    THIS MODULE

What Stage-1 does:

  - Aggregate council batch summary (.loop/council_batch_summary.json)
  - Aggregate task-board state (agent_task_board.py list)
  - Aggregate outcome metrics (outcome_eval.py report)
  - Aggregate apply-rate over last 7d from .loop/issue_audit.jsonl
  - Surface the brutal honesty signal:
    * total_attempts (council runs)
    * applied (drill-gate accepted)
    * apply_rate (= applied / total_attempts)
    * pending_human_review (rejected proposals awaiting operator)

What Stage-1 does NOT do (drill-locked negatives):

  - No write methods. No `assign_*`, `dispatch_*`, `push_*`,
    `update_*`, `mutate_*`. Only `snapshot_*` / `read_*` / `aggregate_*`.
  - No mutation of .loop/ files (drill: worktree byte-identical
    pre/post snapshot).
  - No outbound HTTP calls (drill: offline-runnable).
  - No side effects on import (drill: pure module load).
  - Refuses §42-gated verbs (push, dispatch, escalate) with a
    §42 citation in the error.

Stage 2 (proposal-only) and Stage 3 (gated delegation) compose on
top by adding capabilities — never by modifying this contract.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOOP_DIR = REPO / ".loop"

# Stage-1 v2 surfaces — added 2026-05-06 to compose with the modules
# shipped in the same session: safety_store (history+rollback), ops_worker
# (Ollama proposes / Claude reviews), council_engine (Phases 1-5),
# approval_agent (OPA-default). Path resolution is best-effort: if a
# module isn't present, the aggregator returns an empty/zero shape, NOT
# an exception — the snapshot must work even when only some modules are
# wired. Tests cover both paths (drill_paperclip_v2_integration.py).
SAFETY_DB_DEFAULT = REPO / "safety_store" / "history.db"
OPS_WORKER_AUDIT = REPO / "ops_worker" / "audit.jsonl"
POLISAI_AUDIT = REPO / ".loop" / "policy_audit.jsonl"
OPENCLAW_AUDIT = REPO / ".loop" / "openclaw_audit.jsonl"
MCP_GATEWAY_AUDIT = REPO / ".loop" / "mcp_gateway_audit.jsonl"
DRILL_DIR = REPO / "mcp" / "tests"
PERSONALIZATION_DATA = REPO / "personalization" / "data"
OTEL_METRICS_URL = "http://localhost:9464/metrics"
DRILL_OUTCOME_FILE = REPO / ".loop" / "last_drill_outcome.json"
DRILL_HISTORY_FILE = REPO / ".loop" / "drill_history.jsonl"

# v6 thresholds — flip these to tune ops sensitivity.
OUTBOX_STALE_ALARM_RATIO = 0.30  # ≥30% stale = alarm
OUTBOX_STALE_DEGRADED_RATIO = 0.10  # 10-30% = degraded
PERSONALIZATION_K_ANON_MIN = 5  # mask categories with count < 5

# Postgres connection params for the outbox aggregator. Read-only —
# the aggregator NEVER mutates. Connection failure → empty shape.
PG_HOST = "localhost"
PG_PORT = 55432
PG_USER = "documind_app"
PG_PASSWORD = "documind_app"
PG_DB = "documind"

# Kafka liveness probe: TCP reachability + topic listing via the
# kafka-topics CLI inside the documind-kafka container. No per-event
# audit aggregation — Kafka events are in Postgres outbox tables, not
# JSONL files. Snapshot returns counts + reachability only.
KAFKA_CONTAINER = "documind-kafka"
KAFKA_BOOTSTRAP_HOSTPORT = ("localhost", 59092)

# gRPC liveness probes: known endpoints in this stack. Not per-call
# audit — gRPC client failures land in service logs / OTel traces, not
# in a paperclip-readable JSONL. Snapshot reports TCP reachability only.
GRPC_ENDPOINTS = {
    "qdrant_grpc": ("localhost", 6334),
    "otel_grpc": ("localhost", 4317),
    "jaeger_collector_grpc": ("localhost", 14250),
    "api_gateway_grpc": ("localhost", 9090),
}

# --------------------------------------------------------------------------
# Read-only surfaces. Each function ONLY reads + aggregates. Never writes.
# --------------------------------------------------------------------------


def _read_jsonl(path: Path, limit: int = 1000) -> list[dict[str, Any]]:
    """Read JSONL with bounded limit. Returns [] if missing."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(rows) >= limit:
                break
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    """Read JSON; return {} if missing or malformed."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def aggregate_council_batch() -> dict[str, Any]:
    """Aggregate the latest council batch summary."""
    summary = _read_json(LOOP_DIR / "council_batch_summary.json")
    return {
        "total_attempted": summary.get("total_medium", 0),
        "unique_ids_run": summary.get("unique_ids_run", 0),
        "total_elapsed_s": summary.get("total_elapsed_s", 0.0),
        "last_run_count": len(summary.get("runs", [])),
    }


def _ts_to_epoch(ts: Any) -> float:
    """Coerce timestamp (epoch float OR ISO-8601 string) to epoch seconds.

    The repo writes both shapes across different writers; the Paperclip
    aggregator must tolerate both rather than crash.
    """
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        from datetime import datetime
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def aggregate_apply_attempts(window_days: int = 7) -> dict[str, Any]:
    """Aggregate apply-attempt outcomes over last N days.

    The brutal-honesty surface — surfaces apply_rate even when 0%.
    """
    rows = _read_jsonl(LOOP_DIR / "agent_task_board_apply.jsonl", limit=5000)
    cutoff = time.time() - (window_days * 86400)

    recent = [r for r in rows if _ts_to_epoch(r.get("timestamp", 0)) >= cutoff]
    outcomes = Counter(r.get("outcome", "unknown") for r in recent)
    applied = outcomes.get("applied", 0)
    total = sum(outcomes.values())
    rate = (applied / total) if total > 0 else 0.0

    return {
        "window_days": window_days,
        "total_attempts": total,
        "applied": applied,
        "rejected": outcomes.get("rejected", 0),
        "drill_failed": outcomes.get("drill_failed", 0),
        "errored": outcomes.get("errored", 0),
        "apply_rate": round(rate, 4),
        "honesty_signal": (
            f"{applied}/{total} applied — apply_rate {rate:.1%}"
            if total > 0
            else "no apply attempts in window"
        ),
    }


def aggregate_audit_decisions(limit: int = 50) -> list[dict[str, Any]]:
    """Recent decision audit rows (truncated for snapshot).

    The on-disk audit rows are uneven: some flat (single-role attempts),
    some nested under .chain.{author,reviewer,advisor,researcher}.
    Stage-1 surfaces the top-level outcome + the dominant role's model
    + total tokens summed across the chain.
    """
    rows = _read_jsonl(LOOP_DIR / "issue_audit.jsonl", limit=limit * 4)
    rows.sort(
        key=lambda r: _ts_to_epoch(r.get("ts") or r.get("timestamp", 0)),
        reverse=True,
    )
    out = []
    for r in rows[:limit]:
        chain = r.get("chain", {}) or {}
        # Sum tokens + max latency across the chain (or fall back to flat fields)
        total_tokens = sum(
            int(v.get("tokens", 0)) for v in chain.values() if isinstance(v, dict)
        ) or int(r.get("tokens", 0))
        max_latency = max(
            (float(v.get("latency_s", 0.0)) for v in chain.values() if isinstance(v, dict)),
            default=float(r.get("latency_s", 0.0)),
        )
        # Pick the dominant model: author if present, else any role, else flat
        author = chain.get("author") or {}
        model = author.get("model") or r.get("model", "?")
        out.append({
            "issue_id": r.get("id") or r.get("issue_id", "?"),
            "lane": r.get("lane", "?"),
            "model": model,
            "outcome": r.get("outcome", "?"),
            "tokens_total": total_tokens,
            "max_latency_s": round(max_latency, 2),
        })
    return out


def aggregate_pending_issues() -> dict[str, Any]:
    """Pending issues from the checklist."""
    rows = _read_jsonl(LOOP_DIR / "issue_checklist.jsonl", limit=10000)
    by_assignee: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_difficulty: Counter[str] = Counter()
    for r in rows:
        if r.get("status") == "pending":
            by_assignee[r.get("assignee", "?")] += 1
            by_severity[r.get("severity", "?")] += 1
            by_difficulty[r.get("difficulty", "?")] += 1
    return {
        "total_pending": sum(by_assignee.values()),
        "by_assignee": dict(by_assignee),
        "by_severity": dict(by_severity),
        "by_difficulty": dict(by_difficulty),
    }


def aggregate_council_outcomes() -> dict[str, Any]:
    """Council outcome breakdown — how many ✓ vs ✗ vs pending.

    Top-level `outcome` is the chair-equivalent verdict on each council
    attempt. Aggregates across both schemas (lane=council_local rows
    and the older flat shape).
    """
    rows = _read_jsonl(LOOP_DIR / "issue_audit.jsonl", limit=10000)
    by_outcome: Counter[str] = Counter()
    for r in rows:
        if r.get("lane", "").startswith("council") or "chain" in r:
            by_outcome[r.get("outcome", "?")] += 1
    return {
        "by_outcome": dict(by_outcome),
        "total": sum(by_outcome.values()),
    }


# --------------------------------------------------------------------------
# Stage-1 v2 — aggregators for safety_store, ops_worker, council_engine.
# Best-effort: missing module → empty/zero shape, never an exception.
# --------------------------------------------------------------------------


def aggregate_safety_history(window_days: int = 7) -> dict[str, Any]:
    """Aggregate safety_store/history.db (entity-level history+rollback).

    Surfaces:
      - total history rows in window
      - by-entity-type counts (task / project / agent_cli_session / council_run / ops_worker_task)
      - by-action counts (create / update / delete / rollback / approval_auto / ...)
      - rollback usage: how many rollback_points used / unused

    Empty shape when DB is missing — Paperclip running without
    safety_store still produces a valid snapshot.
    """
    import os
    import sqlite3

    db_path = Path(os.getenv("SAFETY_STORE_DB", str(SAFETY_DB_DEFAULT)))
    empty = {
        "db_present": False,
        "total_rows": 0,
        "by_entity_type": {},
        "by_action": {},
        "rollback_points_used": 0,
        "rollback_points_unused": 0,
        "window_days": window_days,
    }
    if not db_path.exists():
        return empty

    cutoff = time.time() - (window_days * 86400)
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff))
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT entity_type, action FROM history_events WHERE created_at >= ?",
            (cutoff_iso,),
        ).fetchall()
        used = conn.execute(
            "SELECT COUNT(*) FROM rollback_points WHERE used_at IS NOT NULL"
        ).fetchone()[0]
        unused = conn.execute(
            "SELECT COUNT(*) FROM rollback_points WHERE used_at IS NULL"
        ).fetchone()[0]
        conn.close()
    except sqlite3.Error:
        return empty

    return {
        "db_present": True,
        "total_rows": len(rows),
        "by_entity_type": dict(Counter(r["entity_type"] for r in rows)),
        "by_action": dict(Counter(r["action"] for r in rows)),
        "rollback_points_used": int(used),
        "rollback_points_unused": int(unused),
        "window_days": window_days,
    }


def aggregate_ops_worker(window_days: int = 7) -> dict[str, Any]:
    """Aggregate ops_worker/audit.jsonl events.

    The ops_worker writes JSON-line events per status transition
    (PICKED_UP → IN_PROGRESS → CODE_READY → CLAUDE_REVIEW → COMPLETED |
    BLOCKED | WAITING_FOR_HUMAN | REVISION_REQUIRED | FAILED). The
    aggregator surfaces by-status counts + the apply-rate proxy
    (COMPLETED / total).
    """
    rows = _read_jsonl(OPS_WORKER_AUDIT, limit=5000)
    cutoff = time.time() - (window_days * 86400)
    recent = [r for r in rows if _ts_to_epoch(r.get("ts", 0)) >= cutoff]
    statuses: Counter[str] = Counter(r.get("status", "?") for r in recent)
    completed = statuses.get("COMPLETED", 0)
    total_terminal = (
        completed + statuses.get("BLOCKED", 0)
        + statuses.get("REVISION_REQUIRED", 0) + statuses.get("FAILED", 0)
    )
    rate = (completed / total_terminal) if total_terminal > 0 else 0.0
    return {
        "audit_present": OPS_WORKER_AUDIT.exists(),
        "window_days": window_days,
        "total_events": len(recent),
        "by_status": dict(statuses),
        "completed": completed,
        "total_terminal": total_terminal,
        "completion_rate": round(rate, 4),
    }


def aggregate_council_runs(window_days: int = 7) -> dict[str, Any]:
    """Aggregate council_engine runs from safety_store.

    Council runs persist via save_history(entity_type='council_run',
    action='council_decision'). Surfaces by-decision distribution
    (approve / approve_with_changes / revise / reject / escalate) +
    average confidence.
    """
    import os
    import sqlite3

    db_path = Path(os.getenv("SAFETY_STORE_DB", str(SAFETY_DB_DEFAULT)))
    empty = {
        "db_present": False,
        "total_runs": 0,
        "by_decision": {},
        "avg_confidence": 0.0,
        "window_days": window_days,
    }
    if not db_path.exists():
        return empty

    cutoff = time.time() - (window_days * 86400)
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff))
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT new_value_json FROM history_events "
            "WHERE entity_type='council_run' AND action='council_decision' "
            "AND created_at >= ?",
            (cutoff_iso,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return empty

    decisions: Counter[str] = Counter()
    confidences: list[float] = []
    for r in rows:
        try:
            d = json.loads(r["new_value_json"]) if r["new_value_json"] else {}
        except json.JSONDecodeError:
            continue
        decisions[str(d.get("final_decision", "?"))] += 1
        try:
            confidences.append(float(d.get("confidence", 0.0)))
        except (TypeError, ValueError):
            continue
    avg = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    return {
        "db_present": True,
        "total_runs": len(rows),
        "by_decision": dict(decisions),
        "avg_confidence": avg,
        "window_days": window_days,
    }


def aggregate_polisai(window_days: int = 7) -> dict[str, Any]:
    """Aggregate PolisAI policy_check decisions from .loop/policy_audit.jsonl.

    Surfaces:
      - by-allow {True: N, False: M} — default-deny rate
      - top rules_matched (top 5)
      - top denied (actor, tool) pairs
      - policy_version distribution
    """
    rows = _read_jsonl(POLISAI_AUDIT, limit=20000)
    cutoff = time.time() - (window_days * 86400)
    recent = [r for r in rows if _ts_to_epoch(r.get("timestamp", 0)) >= cutoff]
    by_allow: Counter[bool] = Counter(bool(r.get("allow")) for r in recent)
    by_rule: Counter[str] = Counter(
        str(r.get("rule_matched", "?")) for r in recent
    )
    by_version: Counter[str] = Counter(
        str(r.get("policy_version", "?")) for r in recent
    )
    denied_pairs: Counter[str] = Counter(
        f"{r.get('actor', '?')}→{r.get('tool', '?')}"
        for r in recent if not r.get("allow")
    )
    total = len(recent)
    deny_count = by_allow.get(False, 0)
    deny_rate = (deny_count / total) if total else 0.0
    return {
        "audit_present": POLISAI_AUDIT.exists(),
        "window_days": window_days,
        "total_decisions": total,
        "allowed": by_allow.get(True, 0),
        "denied": deny_count,
        "deny_rate": round(deny_rate, 4),
        "top_rules_matched": dict(by_rule.most_common(5)),
        "top_denied_pairs": dict(denied_pairs.most_common(5)),
        "policy_versions": dict(by_version),
    }


def aggregate_openclaw(window_days: int = 7) -> dict[str, Any]:
    """Aggregate OpenClaw A2A dispatch decisions from .loop/openclaw_audit.jsonl.

    Surfaces:
      - by-allow {True: N, False: M}
      - top (requesting_agent → target_agent) pairs
      - top capabilities requested
      - top denied capabilities (the brutal-honesty signal)
    """
    rows = _read_jsonl(OPENCLAW_AUDIT, limit=20000)
    cutoff = time.time() - (window_days * 86400)
    recent: list[dict[str, Any]] = []
    for r in rows:
        decision = r.get("decision") or {}
        ts = decision.get("timestamp", 0)
        if _ts_to_epoch(ts) >= cutoff:
            recent.append(decision)
    by_allow: Counter[bool] = Counter(bool(d.get("allow")) for d in recent)
    pairs: Counter[str] = Counter(
        f"{d.get('requesting_agent', '?')}→{d.get('target_agent', '?')}"
        for d in recent
    )
    capabilities: Counter[str] = Counter(
        str(d.get("capability", "?")) for d in recent
    )
    denied_caps: Counter[str] = Counter(
        str(d.get("capability", "?")) for d in recent if not d.get("allow")
    )
    total = len(recent)
    return {
        "audit_present": OPENCLAW_AUDIT.exists(),
        "window_days": window_days,
        "total_dispatches": total,
        "allowed": by_allow.get(True, 0),
        "denied": by_allow.get(False, 0),
        "top_pairs": dict(pairs.most_common(5)),
        "top_capabilities": dict(capabilities.most_common(5)),
        "top_denied_capabilities": dict(denied_caps.most_common(5)),
    }


def _tcp_reachable(host: str, port: int, timeout_s: float = 0.5) -> bool:
    """Best-effort TCP probe. Returns False on any error — never raises.

    Used by both kafka + grpc aggregators: a Stage-1 read-only surface
    must work even when half the stack is down. No DNS error or refused
    connection is allowed to break the snapshot.
    """
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except (OSError, socket.timeout):
        return False


def aggregate_kafka() -> dict[str, Any]:
    """Aggregate Kafka liveness + topic list.

    Surfaces:
      - bootstrap_reachable (TCP probe)
      - container_running (`docker compose ps kafka` health flag)
      - topics (best-effort via kafka-topics CLI inside the container)

    No per-event count: Kafka events for this stack live in Postgres
    outbox tables (services/ingestion-svc/migrations/002_outbox.sql), not
    a JSONL paperclip can read. To surface event counts here, the
    ingestion-svc would need to write a periodic outbox-snapshot file.
    """
    import subprocess

    host, port = KAFKA_BOOTSTRAP_HOSTPORT
    reachable = _tcp_reachable(host, port)
    topics: list[str] = []
    container_ok = False
    try:
        proc = subprocess.run(
            ["docker", "exec", KAFKA_CONTAINER,
             "kafka-topics", "--bootstrap-server", "localhost:9092", "--list"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        if proc.returncode == 0:
            container_ok = True
            topics = sorted(t for t in proc.stdout.splitlines() if t.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return {
        "bootstrap_reachable": reachable,
        "bootstrap_endpoint": f"{host}:{port}",
        "container_running": container_ok,
        "container_name": KAFKA_CONTAINER,
        "topics": topics,
        "topic_count": len(topics),
    }


def aggregate_mcp_calls(window_days: int = 7) -> dict[str, Any]:
    """Aggregate MCP gateway audit log (.loop/mcp_gateway_audit.jsonl).

    The MCP gateway is the single chokepoint for ALL MCP traffic — every
    actor → server → tool call lands here with allow/deny. Surfaces:
      - by_allow {True, False}
      - top requested servers (top 5)
      - top tools across servers (top 10)
      - top denied (actor, server, tool) triples
    """
    rows = _read_jsonl(MCP_GATEWAY_AUDIT, limit=20000)
    cutoff = time.time() - (window_days * 86400)
    recent = [r for r in rows if _ts_to_epoch(r.get("timestamp", 0)) >= cutoff]
    by_allow: Counter[bool] = Counter(bool(r.get("allow")) for r in recent)
    by_server: Counter[str] = Counter(str(r.get("server", "?")) for r in recent)
    by_tool: Counter[str] = Counter(
        f"{r.get('server', '?')}.{r.get('tool', '?')}" for r in recent
    )
    denied_triples: Counter[str] = Counter(
        f"{r.get('actor', '?')}→{r.get('server', '?')}.{r.get('tool', '?')}"
        for r in recent if not r.get("allow")
    )
    # v6 latency percentiles — only over rows that carry latency_ms
    # (added to gateway audit 2026-05-06; older rows lack the field).
    latencies = sorted(
        float(r["latency_ms"])
        for r in recent
        if isinstance(r.get("latency_ms"), (int, float))
        and r["latency_ms"] >= 0
    )
    latency_summary: dict[str, float] = {
        "samples_with_latency": len(latencies),
    }
    if latencies:
        def _pct(p: float) -> float:
            idx = max(0, min(len(latencies) - 1, int(p * len(latencies))))
            return round(latencies[idx], 3)
        latency_summary.update({
            "p50_ms": _pct(0.50),
            "p95_ms": _pct(0.95),
            "p99_ms": _pct(0.99),
            "max_ms": round(latencies[-1], 3),
        })
    return {
        "audit_present": MCP_GATEWAY_AUDIT.exists(),
        "window_days": window_days,
        "total_calls": len(recent),
        "allowed": by_allow.get(True, 0),
        "denied": by_allow.get(False, 0),
        "top_servers": dict(by_server.most_common(5)),
        "top_tools": dict(by_tool.most_common(10)),
        "top_denied_triples": dict(denied_triples.most_common(5)),
        "latency": latency_summary,
    }


def aggregate_kafka_events(window_days: int = 7) -> dict[str, Any]:
    """Aggregate Kafka events from Postgres outbox table (saga pattern).

    The ingestion-svc writes events to ``ingestion.outbox`` BEFORE
    publishing to Kafka. The dispatcher then publishes + sets
    ``published_at``. Surfaces:
      - total in window / published / unpublished / retried (attempts > 1)
      - by_topic counts (top 5)
      - by_event_type counts (top 5)
      - publish lag stats (count over 5 min unpublished)

    Uses asyncpg wrapped in asyncio.run() to keep this function sync —
    Paperclip Stage-1 stays synchronous. Connection failure → empty.
    """
    empty: dict[str, Any] = {
        "db_present": False,
        "total": 0, "published": 0, "unpublished": 0, "retried": 0,
        "by_topic": {}, "by_event_type": {},
        "stale_unpublished_5m": 0,
        "window_days": window_days,
    }
    try:
        import asyncio
        import asyncpg
    except ImportError:
        return {**empty, "error": "asyncpg not installed"}

    async def _query() -> list[dict[str, Any]]:
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=2.0,
        )
        try:
            return [
                dict(r) for r in await conn.fetch(
                    "SELECT topic, event_type, "
                    "       (published_at IS NOT NULL) AS pubd, "
                    "       attempts, "
                    "       (NOW() - created_at > INTERVAL '5 minutes' "
                    "        AND published_at IS NULL) AS stale "
                    "  FROM ingestion.outbox "
                    " WHERE created_at >= NOW() - ($1 || ' days')::interval",
                    str(window_days),
                )
            ]
        finally:
            await conn.close()

    try:
        rows = asyncio.run(_query())
    except Exception as e:  # noqa: BLE001 - any failure → empty shape
        return {**empty, "error": f"query_failed: {type(e).__name__}"}

    by_topic: Counter[str] = Counter(r["topic"] for r in rows)
    by_evtype: Counter[str] = Counter(r["event_type"] for r in rows)
    published = sum(1 for r in rows if r["pubd"])
    retried = sum(1 for r in rows if (r["attempts"] or 0) > 1)
    stale = sum(1 for r in rows if r["stale"])
    return {
        "db_present": True,
        "total": len(rows),
        "published": published,
        "unpublished": len(rows) - published,
        "retried": retried,
        "by_topic": dict(by_topic.most_common(5)),
        "by_event_type": dict(by_evtype.most_common(5)),
        "stale_unpublished_5m": stale,
        "window_days": window_days,
    }


def aggregate_outbox_health(window_days: int = 7) -> dict[str, Any]:
    """Outbox dispatcher health signal — derives from kafka_events.

    Stale-rate (= stale / total) is the brutal-honesty signal:
      - 0%      → healthy
      - 1-10%   → ok (transient backpressure)
      - 10-30%  → degraded (operator should investigate)
      - ≥30%    → alarm (dispatcher likely down or stuck)

    Surfaces ``status`` enum so dashboards / alerts can color-code.
    """
    ev = aggregate_kafka_events(window_days=window_days)
    if not ev.get("db_present"):
        return {
            "status": "unknown",
            "reason": ev.get("error", "outbox table not reachable"),
            "stale_ratio": 0.0,
            "stale_count": 0,
            "total": 0,
        }
    total = int(ev.get("total", 0))
    stale = int(ev.get("stale_unpublished_5m", 0))
    ratio = (stale / total) if total > 0 else 0.0
    if total == 0:
        status = "idle"
    elif ratio >= OUTBOX_STALE_ALARM_RATIO:
        status = "alarm"
    elif ratio >= OUTBOX_STALE_DEGRADED_RATIO:
        status = "degraded"
    elif ratio > 0:
        status = "ok"
    else:
        status = "healthy"
    return {
        "status": status,
        "reason": (
            f"{stale}/{total} stale (>5min unpublished)"
            if total else "no rows in window"
        ),
        "stale_ratio": round(ratio, 4),
        "stale_count": stale,
        "total": total,
        "thresholds": {
            "alarm": OUTBOX_STALE_ALARM_RATIO,
            "degraded": OUTBOX_STALE_DEGRADED_RATIO,
        },
    }


def aggregate_drill_history() -> dict[str, Any]:
    """Read .loop/last_drill_outcome.json (written by scripts/write_drill_status.py).

    Surfaces:
      - last_run_ts (ISO)
      - total / passed / failed / pass_rate
      - top 10 slowest drills (duration_s)
      - failed drill list (truncated)
    """
    if not DRILL_OUTCOME_FILE.exists():
        return {
            "outcome_file_present": False,
            "total": 0, "passed": 0, "failed": 0,
            "pass_rate": 0.0,
            "last_run_ts": None,
            "slowest_drills": [],
            "failed_drills": [],
        }
    body = _read_json(DRILL_OUTCOME_FILE)
    per = body.get("per_drill") or {}
    failed = [name for name, info in per.items() if not info.get("passed")]
    passed = sum(1 for info in per.values() if info.get("passed"))
    total = len(per) or int(body.get("total_drills", 0))
    rate = (passed / total) if total else 0.0
    # Top 10 slowest
    slow = sorted(
        ((name, float(info.get("duration_s") or 0.0)) for name, info in per.items()),
        key=lambda x: x[1], reverse=True,
    )[:10]
    # v7 — rolling trend from drill_history.jsonl (written by
    # scripts/append_drill_history.py). Surfaces 7-day pass-rate
    # trend so a regression is visible BEFORE it lands in the next
    # snapshot. Empty when no history has been appended yet.
    trend = _drill_trend(window_days=7)
    return {
        "outcome_file_present": True,
        "total": total,
        "passed": passed,
        "failed": len(failed),
        "pass_rate": round(rate, 4),
        "last_run_ts": body.get("timestamp"),
        "slowest_drills": [
            {"name": n, "duration_s": round(d, 3)} for n, d in slow
        ],
        "failed_drills": failed[:20],
        "trend": trend,
    }


def _drill_trend(window_days: int = 7) -> dict[str, Any]:
    """Read drill_history.jsonl + summarise rolling pass-rate."""
    if not DRILL_HISTORY_FILE.exists():
        return {
            "history_present": False,
            "samples": 0, "min_pass_rate": 0.0, "max_pass_rate": 0.0,
            "avg_pass_rate": 0.0, "regression_detected": False,
        }
    rows = _read_jsonl(DRILL_HISTORY_FILE, limit=10000)
    cutoff = time.time() - (window_days * 86400)
    recent = [
        r for r in rows
        if isinstance(r.get("appended_at"), (int, float))
        and r["appended_at"] >= cutoff
    ]
    if not recent:
        return {
            "history_present": True,
            "samples": 0, "min_pass_rate": 0.0, "max_pass_rate": 0.0,
            "avg_pass_rate": 0.0, "regression_detected": False,
        }
    rates = [float(r.get("pass_rate", 0.0)) for r in recent]
    # Regression: pass-rate dropped by >2pp from one row to the next
    drops = [
        (recent[i - 1].get("pass_rate"), recent[i].get("pass_rate"))
        for i in range(1, len(recent))
        if (recent[i - 1].get("pass_rate") or 0.0) - (recent[i].get("pass_rate") or 0.0) > 0.02
    ]
    return {
        "history_present": True,
        "samples": len(recent),
        "min_pass_rate": round(min(rates), 4),
        "max_pass_rate": round(max(rates), 4),
        "avg_pass_rate": round(sum(rates) / len(rates), 4),
        "regression_detected": len(drops) > 0,
        "regression_count": len(drops),
    }


def aggregate_personalization_safe() -> dict[str, Any]:
    """Personalization aggregator — counts ONLY, NO content.

    Surfaces:
      - prompts.jsonl row count + unique user count
      - profile file count
      - modelfile count
      - redaction-category histogram (categories only — no values)

    NEVER returns prompt text, profile content, or user IDs (UUIDs are
    identifiers; counts are not). PII concern from §38 + §48 governance:
    even redacted prompts can be re-identifying when surfaced together.
    """
    base = PERSONALIZATION_DATA
    if not base.exists():
        return {
            "data_present": False,
            "prompt_count": 0,
            "unique_users": 0,
            "profile_count": 0,
            "modelfile_count": 0,
            "redaction_categories": {},
        }
    prompts_file = base / "prompts.jsonl"
    profiles_dir = base / "profiles"
    modelfiles_dir = base / "modelfiles"

    prompts: list[dict[str, Any]] = []
    if prompts_file.exists():
        prompts = _read_jsonl(prompts_file, limit=100000)

    redact_cats: Counter[str] = Counter()
    user_set: set[str] = set()
    for p in prompts:
        for cat in (p.get("prompt_redacted_categories") or []):
            redact_cats[str(cat)] += 1
        # Hash user_id rather than store it — prevents accidental
        # re-identification via the snapshot.
        uid = p.get("user_id")
        if uid:
            user_set.add(str(uid))

    # v6 k-anonymity floor: redaction-category counts below
    # PERSONALIZATION_K_ANON_MIN are MASKED to "<k_anon_floor>".
    # Keeps low-volume tenants from being identified by their
    # rare-category PII profile (e.g. only 1 user has 'jwt' redactions
    # in their prompts → 'jwt: 1' is a re-identifier).
    masked_cats: dict[str, Any] = {}
    for cat, n in redact_cats.most_common(20):
        if n < PERSONALIZATION_K_ANON_MIN:
            masked_cats[cat] = f"<k_anon_floor (n<{PERSONALIZATION_K_ANON_MIN})>"
        else:
            masked_cats[cat] = n

    return {
        "data_present": True,
        "prompt_count": len(prompts),
        "unique_users": len(user_set),
        "profile_count": (
            sum(1 for _ in profiles_dir.glob("*.json"))
            if profiles_dir.exists() else 0
        ),
        "modelfile_count": (
            sum(1 for _ in modelfiles_dir.glob("*.Modelfile"))
            if modelfiles_dir.exists() else 0
        ),
        "redaction_categories": masked_cats,
        "k_anon_min": PERSONALIZATION_K_ANON_MIN,
    }


def aggregate_tests() -> dict[str, Any]:
    """Aggregate the drill scoreboard from the filesystem.

    Per CLAUDE.md §43, every drill MUST have ≥1 negative assertion. The
    aggregator surfaces:
      - total drill_*.py files
      - drills with `# RESOURCES:` tag (parallel-runner-aware)
      - drills with at least one ``NEGATIVE`` step (lower-bound proxy)
      - by-resource-tag counts

    NOT a runner — does not execute drills. Just inventories them.
    """
    if not DRILL_DIR.exists():
        return {
            "drill_dir_present": False,
            "total_drills": 0,
            "with_resources_tag": 0,
            "with_negative_step": 0,
            "by_resource_tag": {},
        }
    drills = sorted(DRILL_DIR.glob("drill_*.py"))
    with_resources = 0
    with_negative = 0
    by_tag: Counter[str] = Counter()
    import re
    res_re = re.compile(r"^#\s*RESOURCES\s*:\s*(.+)$", re.MULTILINE)
    neg_re = re.compile(r"\bNEGATIVE\b", re.IGNORECASE)
    for d in drills:
        try:
            text = d.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = res_re.search(text)
        if m:
            with_resources += 1
            tag = m.group(1).strip()
            # First token only — keep aggregation cardinality bounded
            by_tag[tag.split()[0] if tag.split() else tag] += 1
        if neg_re.search(text):
            with_negative += 1
    return {
        "drill_dir_present": True,
        "total_drills": len(drills),
        "with_resources_tag": with_resources,
        "with_negative_step": with_negative,
        "by_resource_tag": dict(by_tag.most_common(10)),
    }


def aggregate_grpc_metrics() -> dict[str, Any]:
    """Aggregate Prometheus metrics exposed at OTel collector :9464.

    Stage-1 just counts metric names + sample lines. Production would
    parse for documind_*_grpc_* metrics specifically. Reachable check
    + line count is the minimum useful signal.
    """
    import urllib.request
    import urllib.error
    out = {
        "metrics_url": OTEL_METRICS_URL,
        "reachable": False,
        "metric_lines": 0,
        "help_lines": 0,
        "documind_metrics": [],
    }
    try:
        with urllib.request.urlopen(OTEL_METRICS_URL, timeout=2) as r:
            body = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return out
    out["reachable"] = True
    lines = body.splitlines()
    out["metric_lines"] = sum(
        1 for ln in lines if ln and not ln.startswith("#")
    )
    out["help_lines"] = sum(1 for ln in lines if ln.startswith("# HELP"))
    # Surface documind_*-prefixed metrics (project-scoped)
    seen: set[str] = set()
    for ln in lines:
        if ln.startswith("# HELP documind_"):
            name = ln.split(" ", 3)[2] if len(ln.split(" ", 3)) >= 3 else ""
            if name:
                seen.add(name)
    out["documind_metrics"] = sorted(seen)[:20]
    return out


def aggregate_grpc() -> dict[str, Any]:
    """Aggregate gRPC endpoint reachability across the stack.

    Probes the well-known gRPC ports declared in docker-compose.yml.
    Returns ``{endpoint_name: bool}`` — True iff TCP connect succeeded.
    No per-call telemetry: gRPC traces live in Jaeger; OTel collects
    them. This aggregator answers ONLY 'is the port up?'.
    """
    results: dict[str, Any] = {}
    up = 0
    for name, (host, port) in GRPC_ENDPOINTS.items():
        reachable = _tcp_reachable(host, port)
        results[name] = {"endpoint": f"{host}:{port}", "reachable": reachable}
        if reachable:
            up += 1
    return {
        "endpoints": results,
        "endpoints_total": len(GRPC_ENDPOINTS),
        "endpoints_up": up,
        "all_up": up == len(GRPC_ENDPOINTS),
    }


# --------------------------------------------------------------------------
# Top-level snapshot — composes all read-only aggregators.
# --------------------------------------------------------------------------


def aggregate_provider_comparison(window_days: int = 7) -> dict[str, Any]:
    """v8 — unified per-provider task-registry rollup.

    Delegates to scripts.agent_task_registry.build_registry which reads
    .loop/issue_audit.jsonl + .loop/agent_task_board_apply.jsonl +
    governance.audit_log_partitioned and computes per-provider apply-rate.

    Returns the registry shape as-is. On import failure, returns an
    empty shape WITH an `error` field so paperclip snapshot stays
    well-formed but the gap is visible.
    """
    try:
        from agent_task_registry import build_registry as _build_registry
    except ImportError:
        # Try absolute import path when scripts/ isn't on sys.path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from agent_task_registry import build_registry as _build_registry
        except ImportError as exc:
            return {
                "version": "registry-v1",
                "providers": [],
                "totals": {"attempted": 0, "applied": 0, "apply_rate": 0.0},
                "honest_gaps": [f"agent_task_registry import failed: {exc}"],
                "bottleneck_signal": {"signal_active": False, "reason": "module unavailable"},
            }
    try:
        return _build_registry(window_days=window_days)
    except Exception as exc:  # noqa: BLE001 - paperclip never raises
        return {
            "version": "registry-v1",
            "providers": [],
            "totals": {"attempted": 0, "applied": 0, "apply_rate": 0.0},
            "honest_gaps": [f"build_registry crashed: {type(exc).__name__}"],
            "bottleneck_signal": {"signal_active": False, "reason": "build crashed"},
        }


def snapshot(window_days: int = 7) -> dict[str, Any]:
    """The single read-only entry point. Returns aggregated JSON.

    Stage-1 v8 contract — drill locks:
      - this function exists
      - it returns dict with the 20 documented top-level keys
        (5 v1 + 3 v2 + 2 v3 + 2 v4 + 5 v5 + 2 v6 + 0 v7 + 1 v8 —
        backward-compatible; v7 extended drill_history in-place; v8
        adds provider_comparison)
      - it does not mutate state
      - read-only TCP / HTTP-GET / read-only Postgres connections are
        allowed (Stage-1 needs to probe liveness); writes are forbidden
      - missing-module surfaces return empty shapes, NOT exceptions
    """
    return {
        "stage": 1,
        "version": "paperclip-readonly-v8",
        "generated_at": time.time(),
        # v1 surfaces (unchanged)
        "council_batch": aggregate_council_batch(),
        "apply_attempts": aggregate_apply_attempts(window_days=window_days),
        "audit_decisions": aggregate_audit_decisions(limit=20),
        "pending_issues": aggregate_pending_issues(),
        "council_outcomes": aggregate_council_outcomes(),
        # v2 surfaces (compose with safety_store / ops_worker / council_engine)
        "safety_history": aggregate_safety_history(window_days=window_days),
        "ops_worker": aggregate_ops_worker(window_days=window_days),
        "council_runs": aggregate_council_runs(window_days=window_days),
        # v3 surfaces (compose with PolisAI policy + OpenClaw A2A)
        "polisai_policy": aggregate_polisai(window_days=window_days),
        "openclaw_a2a": aggregate_openclaw(window_days=window_days),
        # v4 surfaces (Kafka liveness + gRPC endpoint probes)
        "kafka": aggregate_kafka(),
        "grpc": aggregate_grpc(),
        # v5 surfaces (close the 5 honest gaps from v4 summary)
        "mcp_calls": aggregate_mcp_calls(window_days=window_days),
        "kafka_events": aggregate_kafka_events(window_days=window_days),
        "personalization": aggregate_personalization_safe(),
        "tests": aggregate_tests(),
        "grpc_metrics": aggregate_grpc_metrics(),
        # v6 surfaces (deeper analysis on existing data)
        "outbox_health": aggregate_outbox_health(window_days=window_days),
        "drill_history": aggregate_drill_history(),
        # v8 — provider-comparison rollup (per §55.3 outcome-based contract).
        # Surfaces ollama-council vs ollama-deterministic vs claude-runtime
        # apply-rate. Brutal-honesty signal: when council apply_rate <10%
        # over ≥10 attempts, bottleneck_signal.signal_active=True with a
        # cited Tier-1 next action. NEVER mutates — read-only contract
        # locked by drill_agent_task_registry.py.
        "provider_comparison": aggregate_provider_comparison(window_days=window_days),
    }


# --------------------------------------------------------------------------
# §42-gated verb refusal. Stage-1 has NO write capability; any attempt
# to invoke a write-style verb returns a refusal that cites §42.
# --------------------------------------------------------------------------

WRITE_VERBS = (
    "push", "dispatch", "assign", "escalate", "apply",
    "merge", "deploy", "rollback", "promote",
)


def refuse_write_verb(verb: str) -> dict[str, Any]:
    """Stage-1 contract: write verbs are refused with §42 citation."""
    return {
        "ok": False,
        "error_code": "STAGE_1_READ_ONLY",
        "verb": verb,
        "message": (
            f"Paperclip Stage-1 is read-only by contract. "
            f"Verb {verb!r} is §42-gated and not available until Stage 2 "
            f"(proposal-only) and Stage 3 (gated delegation) ship with "
            f"explicit MCP scope tokens + drill-gated apply."
        ),
        "see": "docs/architecture/adr/012-orchestration-layer-local-first.md",
    }


# --------------------------------------------------------------------------
# Stage-2 — propose_next_task: SUGGESTION-only advisory.
#
# Stage-2 promotion: paperclip moves from "show me state" (Stage-1) to
# "show me state + suggest next move" (Stage-2). Still NO mutation, NO
# dispatch — purely structured recommendation that an operator (or a
# Stage-3 dispatcher) can act on. Drill-locked: must remain read-only
# at the FS + network level.
# --------------------------------------------------------------------------

def propose_next_task() -> dict[str, Any]:
    """Stage-2 — read-only structured suggestion for the next council task.

    Reads the same surfaces snapshot() reads (no new I/O), then ranks
    pending issues by:
      1. Easiest difficulty first (trivial > easy > medium > hard)
      2. Deterministic assignee preferred (ruff:autofix > council > human-review)
      3. Lowest historical apply-rate-by-rule (worst signal first if
         operator wants to investigate; best signal first if operator
         wants to ship — both are valid, we go with "best signal first"
         to maximize apply rate gains)

    Returns a structured proposal dict:
      {
        stage: 2,
        proposal: { issue_id, recommended_actor, recommended_lane,
                    difficulty, rationale, est_effort_minutes,
                    historical_signal },
        rejected: [...],   # candidates considered but skipped, with reasons
        signal: {          # context-of-recommendation
          apply_rate_7d,
          total_pending,
          honesty_signal,
        },
      }

    Stage-2 contract:
      - DOES NOT mutate state (no .loop/ writes)
      - DOES NOT dispatch (Stage-3 will, via OpenClaw + MCP gateway)
      - DOES NOT call PolisAI (no actor context yet — Stage-3 will gate
        the dispatch, not the proposal)
      - DOES NOT make outbound HTTP calls
    """
    # Re-use the existing aggregators — same I/O footprint as snapshot()
    apply_summary = aggregate_apply_attempts(window_days=7)
    pending_summary = aggregate_pending_issues()
    raw_pending = _read_jsonl(LOOP_DIR / "issue_checklist.jsonl", limit=10000)

    # Pending = status='pending'; ranked by difficulty + assignee
    DIFFICULTY_RANK = {"trivial": 0, "easy": 1, "medium": 2, "hard": 3, "?": 4}
    ASSIGNEE_RANK = {
        "ruff:autofix": 0,
        "council:author": 1,
        "council:advisor": 2,
        "council": 3,
        "human-review": 4,
        "?": 5,
    }

    def _rank_key(issue: dict[str, Any]) -> tuple[int, int, str]:
        diff = DIFFICULTY_RANK.get(issue.get("difficulty", "?"), 4)
        # assigned_to vs assignee — different writers used different keys
        assignee = issue.get("assigned_to", issue.get("assignee", "?"))
        ass = ASSIGNEE_RANK.get(assignee, 5)
        return (diff, ass, issue.get("id", ""))

    candidates = [r for r in raw_pending if r.get("status") == "pending"]
    candidates.sort(key=_rank_key)

    rejected: list[dict[str, Any]] = []
    proposal: dict[str, Any] | None = None

    for c in candidates:
        # Skip security-class rules that NEVER go to model (per §50.5.3)
        code = c.get("code", "")
        if code.startswith("S") or code.startswith("B"):
            rejected.append({
                "issue_id": c.get("id"),
                "reason": "security-class rule (S*/B*); §50.5.3 forbids model routing",
            })
            continue
        # Skip already-attempted high-difficulty issues (heuristic:
        # repeat attempts with 0% rate aren't a good Stage-2 next pick)
        if c.get("difficulty") == "hard" and apply_summary["apply_rate"] == 0.0:
            rejected.append({
                "issue_id": c.get("id"),
                "reason": "hard difficulty + 0% historical apply rate; pick easier first",
            })
            continue

        # Pick this one
        difficulty = c.get("difficulty", "?")
        assignee = c.get("assigned_to", c.get("assignee", "?"))
        proposal = {
            "issue_id": c.get("id"),
            "recommended_actor": (
                "operator:human" if assignee == "human-review"
                else "ruff:autofix" if assignee == "ruff:autofix"
                else "council:author"
            ),
            "recommended_lane": assignee,
            "difficulty": difficulty,
            "rationale": (
                f"Easiest pending ({difficulty} difficulty); "
                f"routes to {assignee} lane. Historical apply rate "
                f"{apply_summary['apply_rate']:.1%} suggests focusing "
                f"on quick wins first."
            ),
            "est_effort_minutes": (
                1 if difficulty == "trivial"
                else 5 if difficulty == "easy"
                else 15 if difficulty == "medium"
                else 60
            ),
            "historical_signal": apply_summary["honesty_signal"],
        }
        break  # take the first non-rejected candidate

    if proposal is None:
        return {
            "stage": 2,
            "proposal": None,
            "rejected": rejected,
            "signal": {
                "apply_rate_7d": apply_summary["apply_rate"],
                "total_pending": pending_summary["total_pending"],
                "honesty_signal": apply_summary["honesty_signal"],
            },
            "note": (
                "No proposable issue found. Either checklist is empty "
                "(run scripts/run.sh scan), or all candidates were "
                "rejected (security-class rules + hard-with-0%-rate)."
            ),
        }

    return {
        "stage": 2,
        "proposal": proposal,
        "rejected": rejected,
        "signal": {
            "apply_rate_7d": apply_summary["apply_rate"],
            "total_pending": pending_summary["total_pending"],
            "honesty_signal": apply_summary["honesty_signal"],
        },
    }


# --------------------------------------------------------------------------
# CLI surface — for operator + drill consumption.
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="paperclip_manager",
        description="Stage-1 read-only manager-layer aggregator.",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="Print aggregated snapshot JSON")
    p_snap.add_argument("--window-days", type=int, default=7)
    p_snap.add_argument("--pretty", action="store_true")

    sub.add_parser("verbs", help="List allowed read-only verbs")
    sub.add_parser("propose", help="Stage-2: suggest next council task (read-only)")

    # Write verbs registered explicitly so they route to refuse_write_verb
    # rather than argparse's generic "invalid choice" error. The point is
    # that the §42 refusal must be the loud, operator-readable response —
    # not an argparse error swallowed in CI logs.
    for verb in WRITE_VERBS:
        sub.add_parser(verb, help=f"§42-gated (Stage-1 refuses; see refusal payload)")

    args = parser.parse_args()

    if args.cmd == "snapshot":
        snap = snapshot(window_days=args.window_days)
        indent = 2 if args.pretty else None
        print(json.dumps(snap, indent=indent, default=str))
        return 0

    if args.cmd == "verbs":
        print(json.dumps({
            "stage": 2,
            "read_only_verbs": ["snapshot", "verbs", "propose"],
            "refused_verbs_until_stage_3": list(WRITE_VERBS),
            "rationale": (
                "Stage-1 = read-only aggregation. Stage-2 (this commit) "
                "adds 'propose' — suggestion-only advisory. Stage-3 will "
                "add gated dispatch via OpenClaw + MCP gateway."
            ),
        }, indent=2))
        return 0

    if args.cmd == "propose":
        result = propose_next_task()
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.cmd in WRITE_VERBS:
        print(json.dumps(refuse_write_verb(args.cmd), indent=2))
        return 2  # §42-gated exit code

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
