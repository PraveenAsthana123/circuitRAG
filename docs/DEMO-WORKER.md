# Draft Replay Worker — Autonomous HITL Sweep

**Status:** 🟢 Green. 5-step drill passes.
**Date:** 2026-04-24

Closes:
- `docs/DEMO-HITL.md §"Remaining follow-ups"` row
  "Scheduled replay worker — auto-retries pending drafts with
  exponential backoff after MCP recovery".

The admin API already lets operators replay drafts manually. The worker
is its autonomous counterpart: every N seconds it walks the configured
tenant list, asks `MCPClient.list_pending_drafts`, and replays via
`MCPClient.resolve_draft` — same call path an operator would use, just
without a human in the loop.

---

## What shipped

```
services/inference-svc/
  app/workers/__init__.py          — package marker
  app/workers/draft_replay.py       — DraftReplayWorker
  app/main.py                        — lifespan starts/stops the worker
                                       based on DOCUMIND_REPLAY_WORKER_* env
mcp/tests/drill_worker.py            — 5-step drill
docs/DEMO-WORKER.md                   — this file
```

## Config

```
DOCUMIND_REPLAY_WORKER_ENABLED      true | false       (default: false)
DOCUMIND_REPLAY_WORKER_TENANTS      <uuid>,<uuid>,...  (required when enabled)
DOCUMIND_REPLAY_WORKER_INTERVAL_S   int seconds        (default: 20)
DOCUMIND_REPLAY_WORKER_BACKOFF_S    int seconds        (default: 60)
```

Opt-in by design — the default ops stance is "operator drives replays
via admin API; worker sweeps only when we say so". Turn it on in
staging + prod via config; leave it off in dev unless you explicitly
want background retries.

## Tenant enumeration

The worker requires the tenant list via config rather than discovering
it. Two reasons:

1. **RLS boundary.** The runtime role is NOBYPASSRLS; enumerating
   tenants means crossing the isolation boundary, which is a governance
   decision, not a code decision.
2. **Blast radius control.** A worker that auto-sweeps every tenant by
   default could, if misconfigured, replay aggressively against all
   tenants at once. Making the tenant list explicit forces operators to
   reason about which tenants are in scope.

In production a separate feed (identity-svc, a feature flag, a
dynamic config source) fills the list. Today a CSV env var is enough.

## Backoff model

A small in-memory `{draft_id: last_attempt_monotonic}` map prevents
retrying the same draft every tick. If MCP is flapping, a draft that
failed 5s ago would otherwise get tried on every cycle. `per_draft_backoff_s`
enforces a minimum gap — 60s default.

**Not implemented (deliberate):** exponential backoff per draft. The
`mcp` circuit breaker already handles the "MCP is down, don't hammer"
problem — after `failure_threshold` failures the CB opens and the
worker gets a fast `degraded` response, which triggers an early
cycle bailout. Adding per-draft exponential on top would mask that
signal.

## The 5-step drill

```
── 0. clean slate — delete test-tenant drafts ──
  ✓ drafts cleared

── 1. wire MCPClient + PostgresDraftStore + DraftReplayWorker ──
  ✓ client + store + worker wired (recovery_timeout=3s, backoff=30s)

── 2. kill MCP → create 2 pending drafts ──
  ✓ drafts created: ['DRAFT-7B739C8F82', 'DRAFT-0D6B76EFBE']
  ✓ PG rows: {'pending': 2}

── 3. restart MCP + wait for CB recovery_timeout ──
  ✓ MCP back up

── 4. worker.sweep_once() — both drafts replay ──
  ✓ 2 drafts replayed ok
    worker.stats={'cycles': 1, 'replayed': 2, 'skipped_backoff': 0,
                  'degraded_bailouts': 0, 'errors': 0}

── 5. immediate second sweep — per-draft backoff ──
  ✓ 3rd draft persisted: DRAFT-C766F58102
  ✓ 3rd draft replayed stats.replayed=3
  ✓ second sweep idle (no pending, no errors)

════════════════════════════════════════
  ALL 5 WORKER STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker.py`

## Worker cycle behaviour — failure modes

| Scenario | Worker response |
| --- | --- |
| No pending drafts | cycles++, no work |
| MCP up, drafts pending, resolve succeeds | `replayed++`, PG row → status=replayed |
| MCP down, first resolve returns `degraded=true` | `degraded_bailouts++`, skip rest of cycle |
| MCP timeout / exception during `resolve_draft` | `errors++`, log, continue |
| Draft attempted within backoff window | `skipped_backoff++` |
| `list_pending_drafts` fails (e.g. PG blip) | `errors++`, skip that tenant this cycle |

`worker.stats` is a plain dict — any future metrics layer can scrape
it; current exposure is logs only.

## Interaction with the audit log

Every successful worker replay goes through the same
`MCPClient.resolve_draft` path the admin API uses — which means the
audit log shipped in [DEMO-AUDIT.md](DEMO-AUDIT.md) records them too.
A reader walking `governance.audit_log` sees `mcp_draft.replayed`
rows for operator-driven AND worker-driven replays, with identical
shape. Whether the replay was automated is inferrable only from
`actor_type` + `details.service` — today both paths log the same
`"service"` actor_type. A follow-up can distinguish via
`actor_type="worker"` if it matters for review.

## What's still open

- `actor_type="worker"` on audit rows from this loop — low-effort
  follow-up for operational clarity in the audit view.
- Tenant enumeration from identity-svc instead of env var — swap the
  CSV for an async generator that yields tenants on startup + on a
  periodic refresh.
- Exponential backoff when a specific draft repeatedly fails replay
  (distinct from the per-draft backoff, which is just rate-limiting).
- Metrics endpoint exposing `worker.stats` for Prometheus scrape.
