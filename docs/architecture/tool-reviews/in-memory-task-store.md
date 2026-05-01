# `InMemoryTaskStore` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/store.py`
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 1 | row #35 (UNBOUNDED memory — every task ever submitted accumulates as in-memory dict) |
| **P1** | 1 | row #21 (multi-pod unsafe; clearly documented as fallback only) |
| **P2** | 0 | — |

## Highlights

- ✅ Documented as fallback when Postgres unavailable
- ✅ Used for tests + dev mode

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 35 | Memory-bounded | ✗ | **P0** — `dict[str, TaskView]` with no eviction. Single dev pod accumulating 1000s of tasks across runs leaks. Production deployments lucky to have Postgres available — but the fallback is a memory leak waiting to happen. |
| 36 | Persistent | n/a | InMemory by definition |

## Brutal one-liner

> Single P0: **unbounded memory**. Add `OrderedDict` + LRU eviction at maxlen=1000
> (or whatever fits the dev workload). 15 minutes of work; prevents OOM in any
> long-running dev session that hits the InMemory fallback.
