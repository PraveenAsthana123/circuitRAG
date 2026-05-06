#!/usr/bin/env python3
"""Unified agent task registry — provider-comparison rollup.

Per CLAUDE.md §55.3 outcome-based contract. Per circuitRAG empirical
lesson 2026-05-02: 72 council runs across 3 Ollama models → 0 issues
applied. The bottleneck is council quality. This module surfaces the
per-provider apply-rate so the bottleneck is *visible*, not folklore.

Read-only by contract (§42). Composes with paperclip Stage-1 (§47) as
a v8 surface key. NEVER writes, NEVER dispatches, NEVER pushes.

Sources joined:
  .loop/issue_audit.jsonl          — Ollama per-attempt log
                                     (lane: deepseek-coder|codegemma|codellama|council|ruff:autofix)
  .loop/agent_task_board_apply.jsonl — Apply-gate outcomes
                                       (outcome: applied|rejected)
  .loop/agent_router_audit.jsonl   — Router decisions
                                     (recommended_actor: ollama:*|claude:*|operator:human)
  governance.audit_log_partitioned — Runtime AI decisions
                                     (actor_type: agent|user|system; details JSONB)

Output shape (stable contract — drill-locked):

  {
    "version": "registry-v1",
    "generated_at": <epoch_seconds>,
    "providers": [
      {
        "provider": "ollama-council",
        "attempted": int,    # rows in issue_audit with lane=council
        "applied":   int,    # rows in board_apply with outcome=applied AND lane=council
        "apply_rate": float, # applied/attempted (0.0 if attempted=0)
        "avg_latency_s": float,
        "sample_window_days": int,
      },
      ...
    ],
    "totals": {"attempted": ..., "applied": ..., "apply_rate": ...},
    "honest_gaps": [<list of strings — missing sources / RLS denials>],
  }

The honest_gaps field is the §52 brutal-honesty surface: when a source
is missing or unreachable, the registry says so explicitly rather than
silently zeroing the row.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
LOOP_DIR = REPO / ".loop"

ISSUE_AUDIT = LOOP_DIR / "issue_audit.jsonl"
BOARD_APPLY = LOOP_DIR / "agent_task_board_apply.jsonl"
ROUTER_AUDIT = LOOP_DIR / "agent_router_audit.jsonl"
OPS_TASKS = REPO / "ops_worker" / "tasks.json"

# Postgres for governance.audit_log_partitioned. Read-only.
PG_HOST = os.environ.get("DOCUMIND_PG_HOST", "localhost")
PG_PORT = int(os.environ.get("DOCUMIND_PG_PORT", "55432"))
PG_USER = os.environ.get("DOCUMIND_PG_USER", "documind")
PG_PASSWORD = os.environ.get("DOCUMIND_PG_PASSWORD", "documind")
PG_DB = os.environ.get("DOCUMIND_PG_DB", "documind")

REGISTRY_VERSION = "registry-v2"

# Cost rates — USD per 1M tokens. Ollama lanes are local (GPU energy +
# operator time, NOT directly measurable in dollars), so reported as $0
# with the brutal-honesty caveat that this UNDERSTATES real cost.
# Claude rates can be overridden via env for prompt-cache-aware reads.
# Drill-locked: drill_agent_task_registry.py step 9 verifies the
# Ollama=$0 floor + Claude>$0 reality when synthetic input is provided.
COST_PER_1M_USD_DEFAULT: dict[str, float] = {
    # Ollama — local inference. Cost = $0 in $ but NOT in energy.
    "ollama-council": 0.0,
    "ollama-deterministic": 0.0,
    "ollama-single": 0.0,
    "ollama-other": 0.0,
    # Claude (Sonnet 4.6 typical) — average of $3 input + $15 output / 2 = $9.
    # Operators with input/output split should override via env.
    "claude-runtime": 9.0,
    # agent-orchestrator: cost is sourced FROM the SQL row directly
    # (cost_usd_cents column), NOT from this rate × tokens. The rate
    # is informational only — drilled.
    "agent-orchestrator": 0.0,
}


def _cost_rate_per_1m(provider: str) -> float:
    """Return USD per 1M tokens for ``provider``.

    Reads env override first (e.g. DOCUMIND_COST_RATE_CLAUDE_RUNTIME=12.5),
    falls back to the COST_PER_1M_USD_DEFAULT table. Unknown providers
    get the conservative $0 default — the drill enforces this matches
    the Ollama floor invariant.
    """
    env_key = "DOCUMIND_COST_RATE_" + provider.upper().replace("-", "_")
    env_val = os.environ.get(env_key)
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            log.warning("invalid cost rate env=%s val=%r — using default", env_key, env_val)
    return COST_PER_1M_USD_DEFAULT.get(provider, 0.0)


def _extract_tokens(row: dict[str, Any]) -> int:
    """Extract total tokens from one audit row.

    Council rows store nested chain (author/reviewer/advisor) with each
    contributor's own token count. Single-model rows have a top-level
    `tokens` field. Deterministic rows (ruff:autofix) have neither →
    return 0. Drill-locked: drill step 9 verifies a council row with
    chain={author:300, reviewer:60, advisor:140} returns 500.
    """
    chain = row.get("chain")
    if isinstance(chain, dict):
        total = 0
        for sub in chain.values():
            if isinstance(sub, dict):
                t = sub.get("tokens")
                if isinstance(t, (int, float)):
                    total += int(t)
        return total
    t = row.get("tokens")
    if isinstance(t, (int, float)):
        return int(t)
    return 0

# Lane → provider classification. Council lanes (multi-model author/
# reviewer/advisor chains) all roll up to ollama-council; deterministic
# lanes (ruff:autofix, eslint:autofix) roll up to ollama-deterministic;
# single-model lanes roll up to ollama-single. This mapping is the
# join contract — drill-locked so we can never silently re-classify.
LANE_TO_PROVIDER: dict[str, str] = {
    "council": "ollama-council",
    "council_local": "ollama-council",
    "ruff:autofix": "ollama-deterministic",
    "eslint:autofix": "ollama-deterministic",
    "deterministic": "ollama-deterministic",
}


def _read_jsonl(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
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


def _classify_lane(lane: str) -> str:
    """Map a raw lane string to a stable provider name.

    Single-model lanes (e.g. 'deepseek-coder:6.7b-instruct') roll up
    to ollama-single. Unknown lanes get 'ollama-other' so they're
    visible — never silently dropped.
    """
    if not lane or lane == "unknown":
        return "ollama-other"
    if lane in LANE_TO_PROVIDER:
        return LANE_TO_PROVIDER[lane]
    if ":" in lane and any(m in lane for m in ("coder", "gemma", "llama", "qwen", "mistral")):
        return "ollama-single"
    return "ollama-other"


def _compute_provider_rollup(
    attempts: list[dict[str, Any]],
    applies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-provider rollup: attempted, applied, apply_rate, avg latency.

    Two-pass computation:
      pass 1: count attempts + sum latencies per provider from
              issue_audit.jsonl
      pass 2: count applies per provider from board_apply.jsonl by
              joining on the lane field

    Apply-rate floor: when attempted=0 we report 0.0, NOT division-by-
    zero or NaN. Drill verifies this — a provider with attempted=0
    shows up with apply_rate=0.0 (visible bug surface) instead of
    being dropped.
    """
    by_provider: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "attempted": 0,
            "applied": 0,
            "latency_sum": 0.0,
            "latency_n": 0,
            "tokens_sum": 0,
        }
    )

    for row in attempts:
        provider = _classify_lane(str(row.get("lane", "")))
        by_provider[provider]["attempted"] = int(by_provider[provider]["attempted"]) + 1
        latency = row.get("latency_s")
        if isinstance(latency, (int, float)):
            by_provider[provider]["latency_sum"] = (
                float(by_provider[provider]["latency_sum"]) + float(latency)
            )
            by_provider[provider]["latency_n"] = int(by_provider[provider]["latency_n"]) + 1
        # v2 — sum tokens (top-level OR nested chain). Deterministic rows
        # have neither and contribute 0 (correctly).
        by_provider[provider]["tokens_sum"] = (
            int(by_provider[provider]["tokens_sum"]) + _extract_tokens(row)
        )

    for row in applies:
        if row.get("outcome") != "applied":
            continue
        provider = _classify_lane(str(row.get("lane", "")))
        by_provider[provider]["applied"] = int(by_provider[provider]["applied"]) + 1

    rollup: list[dict[str, Any]] = []
    for provider in sorted(by_provider):
        agg = by_provider[provider]
        attempted = int(agg["attempted"])
        applied = int(agg["applied"])
        latency_n = int(agg["latency_n"])
        tokens_total = int(agg["tokens_sum"])
        avg_latency = (
            float(agg["latency_sum"]) / latency_n if latency_n > 0 else 0.0
        )
        apply_rate = applied / attempted if attempted > 0 else 0.0
        # v2 — cost rollup. cost_usd = tokens × rate / 1_000_000.
        # cost_per_apply = cost_usd / applied (or 0 when applied=0).
        rate_per_1m = _cost_rate_per_1m(provider)
        cost_usd = (tokens_total * rate_per_1m) / 1_000_000.0
        cost_per_apply_usd = (cost_usd / applied) if applied > 0 else 0.0
        rollup.append({
            "provider": provider,
            "attempted": attempted,
            "applied": applied,
            "apply_rate": round(apply_rate, 4),
            "avg_latency_s": round(avg_latency, 2),
            "latency_samples": latency_n,
            # v2 — cost surface
            "tokens_total": tokens_total,
            "cost_rate_usd_per_1m": rate_per_1m,
            "cost_usd": round(cost_usd, 6),
            "cost_per_apply_usd": round(cost_per_apply_usd, 6),
        })
    return rollup


def _read_orchestrator_runs(window_days: int = 7) -> tuple[dict[str, Any], str | None]:
    """Read agent-orchestrator runs from orchestration.agent_task_runs.

    The unified-task SQL schema already exists at
    orchestration.agent_tasks + .agent_task_runs (v8 of governance-svc
    migrations). The registry composes them in as a separate provider
    lane — `agent-orchestrator` — so operators see runtime task
    activity in the same per-provider table as Ollama council attempts.

    Per §47.7 expand-phase: this is read-only composition. The
    repository never writes; the orchestration service is the
    write-side and can dual-write JSONL during the migration window.

    Returns ({attempted, applied, tokens_total, cost_usd, latency_sum,
              latency_n}, gap_reason).

    gap_reason is non-None when:
      - postgres unreachable
      - asyncpg missing
      - table empty (informational; not a failure)

    RLS note: queries the table without setting app.current_tenant.
    With FORCE ROW LEVEL SECURITY (orchestration.agent_task_runs
    has RLS per the §43.4 contract), this returns 0 rows in
    operator-context. The drill verifies this by inserting a test
    row in a transaction with a tenant context, querying without
    context, expecting 0.
    """
    empty: dict[str, Any] = {
        "attempted": 0, "applied": 0,
        "tokens_total": 0, "cost_usd": 0.0,
        "latency_sum": 0.0, "latency_n": 0,
    }
    try:
        import asyncio

        import asyncpg
    except ImportError:
        return empty, "asyncpg not installed (agent-orchestrator rollup skipped)"

    async def _query() -> dict[str, Any]:
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=2.0,
        )
        try:
            row = await conn.fetchrow(
                "SELECT count(*) AS n, "
                "       count(*) FILTER (WHERE status = 'completed') AS applied, "
                "       coalesce(sum(coalesce(tokens_in, 0) + coalesce(tokens_out, 0)), 0)::int AS tokens, "
                "       coalesce(sum(coalesce(cost_usd_cents, 0)), 0)::int AS cents, "
                "       coalesce(sum(duration_ms), 0)::bigint AS lat_sum_ms, "
                "       count(*) FILTER (WHERE duration_ms IS NOT NULL) AS lat_n "
                "  FROM orchestration.agent_task_runs "
                " WHERE created_at >= NOW() - ($1 || ' days')::interval",
                str(window_days),
            )
            if row is None:
                return dict(empty)
            return {
                "attempted": int(row["n"]),
                "applied": int(row["applied"] or 0),
                "tokens_total": int(row["tokens"] or 0),
                # cost_usd_cents → dollars
                "cost_usd": float(row["cents"] or 0) / 100.0,
                "latency_sum": float(row["lat_sum_ms"] or 0) / 1000.0,
                "latency_n": int(row["lat_n"] or 0),
            }
        finally:
            await conn.close()

    try:
        result = asyncio.run(_query())
    except Exception as exc:
        return empty, f"orchestration tables unreachable: {type(exc).__name__}"

    if result["attempted"] == 0:
        return result, (
            "orchestration.agent_task_runs is empty (RLS-scoped or no runs in "
            "window) — agent-orchestrator service may not be writing yet, OR "
            "the operator context lacks app.current_tenant. Drill verifies "
            "the read path is correct by round-tripping a synthetic row."
        )
    return result, None


def _read_runtime_ai_decisions(window_days: int = 7) -> tuple[int, str | None]:
    """Read runtime-AI decision count from governance.audit_log_partitioned.

    Returns (count, gap_reason). gap_reason is None on success, a
    short string when the source is unreachable. Per §43.4 RLS
    isolation drill expectation: an operator-context read (no
    tenant GUC set) returns 0 rows — the gap explains why.

    Uses asyncpg (already a paperclip_manager.py dependency) wrapped
    in asyncio.run() so this caller stays synchronous.
    """
    try:
        import asyncio

        import asyncpg
    except ImportError:
        return 0, "asyncpg not installed (runtime-AI rollup skipped)"

    async def _query() -> int:
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=2.0,
        )
        try:
            row = await conn.fetchrow(
                "SELECT count(*) AS n FROM governance.audit_log_partitioned "
                "WHERE actor_type = 'agent' "
                "AND timestamp > NOW() - ($1 || ' days')::interval",
                str(window_days),
            )
            return int(row["n"]) if row else 0
        finally:
            await conn.close()

    try:
        count = asyncio.run(_query())
    except Exception as exc:
        return 0, f"postgres unreachable: {type(exc).__name__}"

    if count == 0:
        return 0, (
            "RLS-scoped read returned 0 rows (no tenant GUC set; "
            "expected for operator-context — runtime-AI traffic is "
            "tenant-scoped and counted via OTel histograms in production)"
        )
    return count, None


def build_registry(window_days: int = 7) -> dict[str, Any]:
    """Build the unified agent-task registry snapshot.

    Read-only. Returns empty/zero rows for missing sources, listing
    them in `honest_gaps`. Drill-locked: the contract is the shape
    plus the §42 read-only invariant.
    """
    gaps: list[str] = []

    attempts = _read_jsonl(ISSUE_AUDIT)
    if not ISSUE_AUDIT.exists():
        gaps.append(f"missing: {ISSUE_AUDIT.name}")

    applies = _read_jsonl(BOARD_APPLY)
    if not BOARD_APPLY.exists():
        gaps.append(f"missing: {BOARD_APPLY.name}")

    providers = _compute_provider_rollup(attempts, applies)

    # Runtime-AI lane (Claude / agent-orchestrator runtime decisions).
    # Surfaced as a separate provider row even when count=0 so the
    # comparison view always shows the slot.
    runtime_count, runtime_gap = _read_runtime_ai_decisions(window_days=window_days)
    if runtime_gap:
        gaps.append(runtime_gap)
    # agent-orchestrator: read from orchestration.agent_task_runs (the
    # unified-task SQL surface). Per §47.7 expand phase — read-only
    # composition. Empty rollup with honest_gap when the table has 0
    # rows in the window (orchestrator service not writing yet, OR
    # operator-context RLS scope returns 0). Drill verifies the query
    # is correct by round-tripping a synthetic row in a temp tx.
    orch_stats, orch_gap = _read_orchestrator_runs(window_days=window_days)
    if orch_gap:
        gaps.append(orch_gap)
    orch_lat_n = int(orch_stats.get("latency_n", 0))
    orch_lat_sum = float(orch_stats.get("latency_sum", 0.0))
    orch_avg_latency = (orch_lat_sum / orch_lat_n) if orch_lat_n > 0 else 0.0
    orch_attempted = int(orch_stats.get("attempted", 0))
    orch_applied = int(orch_stats.get("applied", 0))
    orch_tokens = int(orch_stats.get("tokens_total", 0))
    orch_cost = float(orch_stats.get("cost_usd", 0.0))
    orch_apply_rate = (orch_applied / orch_attempted) if orch_attempted > 0 else 0.0
    orch_cost_per_apply = (orch_cost / orch_applied) if orch_applied > 0 else 0.0
    providers.append({
        "provider": "agent-orchestrator",
        "attempted": orch_attempted,
        "applied": orch_applied,
        "apply_rate": round(orch_apply_rate, 4),
        "avg_latency_s": round(orch_avg_latency, 2),
        "latency_samples": orch_lat_n,
        "tokens_total": orch_tokens,
        # Cost rate is informational; cost_usd is read directly from
        # the SQL cost_usd_cents column (NOT computed from rate × tokens).
        "cost_rate_usd_per_1m": _cost_rate_per_1m("agent-orchestrator"),
        "cost_usd": round(orch_cost, 6),
        "cost_per_apply_usd": round(orch_cost_per_apply, 6),
        "note": (
            "sourced from orchestration.agent_task_runs (SQL); cost_usd reads "
            "cost_usd_cents directly (NOT rate×tokens). Per §47.7 expand-phase: "
            "JSONL surfaces remain authoritative until contract phase."
        ),
    })

    # claude-runtime: tokens not yet aggregated from Postgres details
    # JSONB in this iteration — left as a documented gap. The audit row
    # exists; the cost column reads $0 + an honest_gap until the next
    # iteration extends the asyncpg query to read details->>'tokens'.
    providers.append({
        "provider": "claude-runtime",
        "attempted": runtime_count,
        "applied": runtime_count,  # runtime decisions ARE the apply
        "apply_rate": 1.0 if runtime_count > 0 else 0.0,
        "avg_latency_s": 0.0,  # OTel histograms hold the truth here
        "latency_samples": 0,
        "tokens_total": 0,
        "cost_rate_usd_per_1m": _cost_rate_per_1m("claude-runtime"),
        "cost_usd": 0.0,
        "cost_per_apply_usd": 0.0,
        "note": (
            "apply_rate=1.0 by definition: runtime decisions log only when executed. "
            "tokens_total=0 because details->>'tokens' aggregation not yet wired "
            "(deferred to next iteration to keep this commit tight)."
        ),
    })
    if runtime_count > 0:
        gaps.append(
            "claude-runtime cost rollup deferred — tokens column reads 0 until "
            "details->>'tokens' aggregation lands in registry-v3"
        )

    total_attempted = sum(int(p["attempted"]) for p in providers)
    total_applied = sum(int(p["applied"]) for p in providers)
    total_tokens = sum(int(p.get("tokens_total", 0)) for p in providers)
    total_cost_usd = sum(float(p.get("cost_usd", 0.0)) for p in providers)
    overall_apply_rate = (
        total_applied / total_attempted if total_attempted > 0 else 0.0
    )

    return {
        "version": REGISTRY_VERSION,
        "generated_at": time.time(),
        "window_days": window_days,
        "providers": providers,
        "totals": {
            "attempted": total_attempted,
            "applied": total_applied,
            "apply_rate": round(overall_apply_rate, 4),
            # v2 — cost totals
            "tokens_total": total_tokens,
            "cost_usd": round(total_cost_usd, 6),
        },
        "honest_gaps": gaps,
        # Bottleneck signal — the headline number §55 wants visible.
        # When ollama-council apply_rate < 0.10 over a non-trivial
        # sample, Tier 1.1 (Pydantic schema enforcement) is the
        # justified next iteration.
        "bottleneck_signal": _detect_bottleneck(providers),
    }


def _detect_bottleneck(providers: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect the §55 council-bottleneck signal.

    Returns a dict with signal_active (bool), reason (str), and
    suggested_action (str). Threshold: ≥10 attempts AND apply_rate < 0.10.
    Below 10 attempts, signal is suppressed (sample too small).
    """
    council = next((p for p in providers if p["provider"] == "ollama-council"), None)
    if council is None:
        return {"signal_active": False, "reason": "no council samples"}
    attempted = int(council["attempted"])
    apply_rate = float(council["apply_rate"])
    if attempted < 10:
        return {
            "signal_active": False,
            "reason": f"council sample too small (attempted={attempted}, threshold=10)",
        }
    if apply_rate < 0.10:
        return {
            "signal_active": True,
            "reason": f"council apply_rate={apply_rate:.2%} over {attempted} attempts",
            "suggested_action": (
                "Implement §55 Tier 1.1 (Pydantic CouncilProposal schema) — "
                "schema-validation rejects malformed proposals before git apply --check"
            ),
            "policy_ref": "CLAUDE.md §55.2 Tier 1",
        }
    return {
        "signal_active": False,
        "reason": f"council apply_rate={apply_rate:.2%} above 10% threshold",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window-days", type=int, default=7,
        help="Lookback window for apply-rate computation",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON snapshot to stdout",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Emit human-readable per-provider table",
    )
    args = parser.parse_args()

    snapshot = build_registry(window_days=args.window_days)

    if args.json or not args.summary:
        json.dump(snapshot, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    # Human summary — v2 adds tokens + cost columns
    print(f"agent-task registry — version={snapshot['version']}")
    print(f"window={snapshot['window_days']}d  generated_at={snapshot['generated_at']:.0f}")
    print()
    print(
        f"{'provider':<25} {'attempted':>9} {'applied':>8} "
        f"{'apply_rate':>10} {'avg_lat':>8} {'tokens':>10} {'cost_usd':>10}"
    )
    print("-" * 88)
    for p in snapshot["providers"]:
        print(
            f"{p['provider']:<25} {p['attempted']:>9} {p['applied']:>8} "
            f"{p['apply_rate']:>10.2%} {p['avg_latency_s']:>8.2f} "
            f"{p.get('tokens_total', 0):>10} ${p.get('cost_usd', 0.0):>9.4f}"
        )
    print("-" * 88)
    t = snapshot["totals"]
    print(
        f"{'TOTAL':<25} {t['attempted']:>9} {t['applied']:>8} "
        f"{t['apply_rate']:>10.2%} {' ':>8} "
        f"{t.get('tokens_total', 0):>10} ${t.get('cost_usd', 0.0):>9.4f}"
    )

    if snapshot["honest_gaps"]:
        print("\nhonest_gaps:")
        for gap in snapshot["honest_gaps"]:
            print(f"  - {gap}")

    bs = snapshot["bottleneck_signal"]
    print(f"\nbottleneck_signal: {'ACTIVE' if bs['signal_active'] else 'inactive'}")
    print(f"  reason: {bs['reason']}")
    if bs.get("suggested_action"):
        print(f"  action: {bs['suggested_action']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
