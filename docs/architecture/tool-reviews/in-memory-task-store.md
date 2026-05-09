# `InMemoryTaskStore` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/store.py`
**Date:** 2026-05-01 (review) · 2026-05-08 (P0 closure verified)

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | row #35 closed — `OrderedDict` + LRU eviction shipped (max_tasks=1000) |
| **P1** | 1 | row #21 (multi-pod unsafe; clearly documented as fallback only) |
| **P2** | 0 | — |

## Highlights

- ✅ Documented as fallback when Postgres unavailable
- ✅ Used for tests + dev mode
- ✅ **P0 #35 closed**: `_items: OrderedDict[str, TaskView]` with `_evict_if_over(od, cap)` LRU eviction; `save()` calls `move-to-end` to refresh recency, then evicts oldest when over `max_tasks` (default 1000). Per-task run history bounded by `max_runs_per_task` (default 100); per-scope memories bounded by `max_memories_per_scope` (default 200); projects bounded by `max_projects` (default 500). All caps overridable via constructor.

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 35 | Memory-bounded | ✓ | **P0 CLOSED** — `OrderedDict` per-collection caps with LRU eviction. See `_evict_if_over` + `_DEFAULT_MAX_*` constants. Verified by code-read of `services/agent-orchestrator-svc/app/store.py` lines 18-56, 64, 112, 152, 176. |
| 36 | Persistent | n/a | InMemory by definition |

## Brutal one-liner

> Was: Single P0 unbounded memory. NOW: closed via `OrderedDict` + LRU
> eviction at maxlen=1000 (configurable). 4 caps applied in total
> (tasks / runs-per-task / projects / memories-per-scope). 15 minutes
> of work, as predicted. P1 (multi-pod unsafe) remains by design —
> InMemory is the dev/test fallback; PostgresTaskStore is the
> multi-pod path.
