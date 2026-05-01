# Testing Guide

> §19 mandate. The substantive content for THIS project lives at:
>
> See: [`docs/ci-drills-setup.md`](ci-drills-setup.md) — drill harness setup
> See: [`mcp/tests/drill_*.py`](../mcp/tests/) — 200+ drills (real-stack tests)
> See: [§43 Drill Pattern in `~/.claude/policies/drill-testing-pattern.md`](../../.claude/policies/drill-testing-pattern.md)

## Why this stub exists

The global CLAUDE.md §19 names a specific doc path. circuitRAG's
testing strategy is encoded in:

- **210+ drills** under `mcp/tests/drill_*.py` — real-stack tests
  hitting docker-compose services with negative assertions per §43.
- **`scripts/run_drills.py`** — resource-aware parallel runner.
- **`mcp/server_drills.py`** — MCP-exposed drill server with
  scope-gated `drill.run` / `drill.list`.
- **Per-service tests** — see [DEMO-SERVICE-SMOKE.md](DEMO-SERVICE-SMOKE.md).
- **Coverage ratchet** — `pyproject.toml`'s
  `[tool.coverage.report] fail_under` floor only goes UP. Comments
  document every uplift.

This stub redirects rather than duplicates. The real source-of-truth
files above evolve faster than a hand-curated guide ever could.

## When to write what kind of test

| Surface | Tool | Example |
|---|---|---|
| Service /health probe | Per-service smoke (TestClient or httptest) | `services/*/tests/`, `services/*/cmd/main_test.go` |
| Cross-service workflow | Drill (Python, `mcp/tests/`) | `drill_e2e_admin_smoke.py` |
| Frontend rendering | Playwright (Python harness or `npm run test:e2e`) | `services/frontend/e2e/admin-smoke.spec.ts` |
| Library unit | pytest under `libs/py/tests` | `libs/py/tests/test_*.py` |
| Compose-footer compliance | Drill — static grep | `drill_e2e_admin_smoke.py` step 1 |

## §43 drill rules

Every feature commit ships a drill. Every drill has at least one
negative assertion. See [`drill-testing-pattern.md`](../../.claude/policies/drill-testing-pattern.md).
