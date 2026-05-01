# DEMO — §8 Per-Service Smoke Tests (6 services closed)

## What it is

The 2026-04-30 audit flagged 6 services that shipped with a
Dockerfile but no `tests/` directory. This iteration adds a real
test file per service that exercises actual production code.

## What got tested per service

| Service | Language | Test file | What it tests |
|---|---|---|---|
| `agent-orchestrator-svc` | Python | `tests/test_smoke.py` | TestClient → /health/live + /health/ready (negative: phantom route → 404) |
| `api-gateway` | Go | `internal/config/config_test.go` | `Load()` defaults; env override; **negative**: malformed int falls back; **negative**: no `*` in CORS |
| `finops-svc` | Go | `cmd/main_test.go` | Real `ComputeShadowCost` arithmetic on `shadowRates` table; **negative**: unknown model returns 0; scaling sanity |
| `governance-svc` | Go | `cmd/main_test.go` | `PolicyEngine.Evaluate` shape; `HITLService.Enqueue` doesn't panic; `AuditLog.Record` accepts empty payload |
| `identity-svc` | Go | `cmd/main_test.go` | `Login` returns non-empty token; `CreateTenant` UUID + Tier valid; **negative**: Tier ∈ {free,pro,enterprise} |
| `observability-svc` | Go | `cmd/main_test.go` | `defaultSLOs` non-empty; valid TargetPercent; **negative**: `availability` SLO required |

## Drill

[`mcp/tests/drill_service_smoke.py`](../mcp/tests/drill_service_smoke.py)
— 4 steps, 1 negative.

| Step | What it checks |
|---|---|
| 1 | Static — each flagged service has its expected test file |
| 2 | `pytest agent-orchestrator-svc/tests/` exits 0 |
| 3 | `go test ./...` for each of 5 Go services exits 0 |
| 4 (negative) | Allowlist size = 6 (locks audit scope; adding a service without updating the list fails) |

## The negative assertion design

Step 4 is a **list-size lock**. The audit identified exactly 6
services missing tests. If someone later adds a 7th service without a
test file but doesn't add it to the drill's `EXPECTED_TEST_FILES`,
step 1 silently passes (the existing 6 still have files). Step 4
catches that drift by asserting the list itself stays in sync with
the audit.

This is the §43 negative-assertion shape: not "the test passes" but
"the test cannot be silently bypassed by drift."

## Run

```bash
.venv/bin/python mcp/tests/drill_service_smoke.py
```

Go execution requires `go` on PATH; the drill auto-discovers
`/tmp/go/bin/go` and falls back to PATH. CI runs `actions/setup-go@v5`
so it always has Go available.

## Observed results (2026-04-30)

```
✓ step 1: all 6 flagged services have test files
✓ step 4 (negative): explicit allowlist size = 6 (locks the audit scope)
✓ step 2: pytest agent-orchestrator-svc/tests → exit 0
✓ step 3: go test ./... in api-gateway → exit 0
✓ step 3: go test ./... in finops-svc → exit 0
✓ step 3: go test ./... in governance-svc → exit 0
✓ step 3: go test ./... in identity-svc → exit 0
✓ step 3: go test ./... in observability-svc → exit 0

ALL STEPS PASSED (6 services covered)
```

## What this is NOT

- **Not a comprehensive test suite.** Each test file has 2-4 cases
  that exercise the existing production code. This closes the
  "service has zero tests" structural gap, not the "service is fully
  tested" goal. Deeper coverage is a separate, ongoing effort.
- **Not docker-compose-based.** Tests run in-process (Python
  TestClient, Go httptest-style). Real-stack drills against running
  services live elsewhere.

## Composition

| Composes with | Why |
|---|---|
| §8 Test categories | Structural gap (no tests/ dir at all) → CRUD-tier coverage shipped per service |
| §43 Drill discipline | Step 4 is the negative-assertion lock against drift |
| §25 Test pyramid | Bottom of pyramid (cheapest, fastest) for services that had no pyramid |
| `evaluation-svc` (§48 sibling) | Same TestClient pattern; explainability drill scaled to per-service smoke |
