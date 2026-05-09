# `TesterAgent` + `mcp_tests` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/tester.py` + `mcp/server_tests.py`
**Date:** 2026-05-01 (review) · 2026-05-09 (P0 #34 closure verified)

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | row #34 closed: `mcp/server_tests.py` lines 45-67 — `_ACTIVE_PROCS: set[asyncio.subprocess.Process]` tracks in-flight subprocesses; `_lifespan` shutdown handler kills + awaits all running children before allowing exit; 6 add/discard sites cover success+timeout paths × 3 runners (ruff/pytest/mypy). Drilled by `drill_p0_mcp_graceful_shutdown.py` 7/7 — empirical TestClient enter/exit + structural kill-wait-clear assertions. |
| **P1** | 4 | rows #10 (no concurrent-subprocess cap; 100 simultaneous calls fork 100 ruff), #21 (no result cache), #36 (no breaker on tests subprocess), #38 (no deadletter for crashed subprocess) |
| **P2** | 3 | rows #18, #19, #22 |

## Highlights

- ✅ Real subprocess via `asyncio.create_subprocess_exec` (argv list, no shell)
- ✅ Path-traversal-proof `_validate_target` against `ALLOWED_TARGET_ROOTS`
- ✅ 60s timeout on ruff, 120s on mypy
- ✅ pytest is `--collect-only` (read-only)

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 10 | Concurrency cap on subprocess | ✗ | **P1** — server admits N concurrent ruff invocations; CPU saturation under load |
| 21 | Result cache | ✗ | **P1** — same (target, runner) → re-runs the subprocess every time |
| 23 | Cost of failures | n/a | local subprocess is free, but CPU/RAM spike is real |
| 24 | Rollback signal | ⚠ | Test failure flows to coder retry, but not to observer's signal |
| 25 | Audit row | ✗ | Tests results NOT in `/explain` row |
| 33 | Rate limit | ✗ | **P1** — flood `/tools/call` → fork bomb |
| 34 | Graceful shutdown | ✗ | **P0** — subprocess children orphaned on SIGTERM (`asyncio.wait_for` cancellation does NOT kill children automatically — need `proc.kill()` in finally) |
| 36 | Dep CB | ✗ | **P1** — slow ruff (1 of 60s timeout) takes 60s; no fast-fail |
| 38 | Deadletter | ✗ | Crashed subprocess → log + return; no quarantine |

## Brutal one-liner

> The path-validation + subprocess hygiene is **excellent** for a stub MCP server.
> What it's missing is **fleet-of-subprocesses** discipline: no concurrent cap,
> no caching, no SIGTERM cleanup. Under load, this server fork-bombs your CPU.
> Fix #34 (orphan subprocesses) FIRST — it's a leak that grows without bound.
