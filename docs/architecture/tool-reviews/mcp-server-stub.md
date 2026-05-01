# MCP Server Pattern (research / tests / deploy / observe stubs) — Brutal Tool Review

**Source:** `mcp/server_research.py`, `mcp/server_tests.py`, `mcp/server_deploy.py`, `mcp/server_observe.py`
**Date:** 2026-05-01

## Triage (worst-case across the 4 servers)

| Severity | Count | Top items |
|---|---|---|
| **P0** | 1 | row #34 (no graceful shutdown drains in-flight requests; no signal handler) |
| **P1** | 3 | rows #5 (broad except in handlers), #11 (no slow-call detect), #36 (no breaker around upstream Prom/AM/etc.) |
| **P2** | 3 | rows #19, #20, #22 |

## Per-server status

| Server | Real backings | Stub state | P0 | P1 |
|---|---|---|---|---|
| mcp_research | httpx (E6) | partial | 0 | 1 |
| mcp_tests | ruff/pytest/mypy (E2,E5) | partial | 1 | 1 |
| mcp_deploy | none (canned) | full stub | 0 | 1 |
| mcp_observe | Prom (E3) + AM (E4) | none | 0 | 1 |

## Common gaps across all 4

| # | Dim | Status | Note |
|---|---|---|---|
| 5 | Narrow exception scope | ⚠ | `except (httpx.HTTPError, httpx.TimeoutException)` is good; many handlers still have `except Exception` blocks |
| 13 | Latency histogram | ✗ | `mount_metrics_endpoint` not wired on stubs (only on canonical mcp servers) |
| 18 | Drill — server-side | ⚠ | Each has a drill; none have load tests |
| 19 | Manual override | ✗ | Operator can't disable a tool from the server side ("research.synthesize is misbehaving — block it") |
| 33 | Rate limit | ✗ | Per-tenant rate limit not enforced at server boundary |
| 34 | Graceful shutdown | ✗ | **P0** — uvicorn default; no in-flight drain; no `shutdown` handler closes httpx.AsyncClient sessions |
| 36 | Dep CB | ✗ | mcp_observe → Prom/AM has no CB; mcp_research → httpx has no CB; mcp_tests → subprocess has no per-runner CB |

## Brutal one-liner

> The 4 stubs follow a clean shared pattern. **One P0 across them all** — no
> graceful shutdown. Under SIGTERM during a soak window, in-flight Prom queries
> get killed mid-stream. Add a shared shutdown handler in `server_common.py`;
> all 4 inherit it.
