# Repo Deep Test Plan

This note maps deep testing to the actual services, files, and tooling already present in this repo.

It is not a complete test implementation.
It is a practical plan for what to test, where to test it, and what commands or surfaces already exist.

## 1. Current Test Surfaces In The Repo

### Python services

Existing Python test directories:

- `services/inference-svc/tests`
- `services/ingestion-svc/tests`
- `services/retrieval-svc/tests`
- `services/evaluation-svc/tests`

Repo-level Python test config is also present in [pyproject.toml](/mnt/deepa/rag/pyproject.toml:1).

### Frontend

The frontend already documents `vitest` in:

- [services/frontend/README.md](/mnt/deepa/rag/services/frontend/README.md:1)
- [services/frontend/package.json](/mnt/deepa/rag/services/frontend/package.json:1)

### CI

GitHub Actions already runs:

- Python lint, security, and pytest
- Go `vet`, `build`, and `test -race`
- frontend build
- docker builds
- infra validation

See:

- [.github/workflows/ci.yml](/mnt/deepa/rag/.github/workflows/ci.yml:1)

## 2. Current Command Surfaces

### Repo and Python core

Common existing CI commands:

```bash
ruff check libs/py services/ingestion-svc/app services/retrieval-svc/app services/inference-svc/app services/evaluation-svc/app scripts
black --check libs/py services/ingestion-svc/app services/retrieval-svc/app services/inference-svc/app services/evaluation-svc/app
pycodestyle --max-line-length=120 libs/py services/ingestion-svc/app services/retrieval-svc/app services/inference-svc/app services/evaluation-svc/app
mypy --ignore-missing-imports libs/py/documind_core
bandit -r libs/py services/ingestion-svc/app services/retrieval-svc/app services/inference-svc/app services/evaluation-svc/app -ll
pytest -q libs/py/tests --cov=libs/py/documind_core --cov-report=term-missing
```

### Frontend

```bash
cd services/frontend
npm run test
npm run build
npm run lint
```

### Go services

For each Go service:

```bash
go vet ./...
go build -v ./...
go test -race -count=1 ./...
```

## 3. Service-By-Service Deep Testing Plan

## 3.1 Frontend

Relevant areas:

- [services/frontend/app](/mnt/deepa/rag/services/frontend/app)
- [services/frontend/components](/mnt/deepa/rag/services/frontend/components)
- [services/frontend/lib](/mnt/deepa/rag/services/frontend/lib)

### High-value tests

- page load states for `ask`, `upload`, `documents`, and `admin`
- frontend handling of failed API responses
- browser-console cleanliness
- mobile navigation and responsive shell behavior
- route-level error boundary behavior
- API client error-envelope parsing

### F12 and browser checks

- network failures render useful errors
- no hydration or chunk-load issues
- no broken navigation links
- no obvious console exceptions on core routes

## 3.2 API Gateway

Relevant areas:

- [services/api-gateway/cmd/main.go](/mnt/deepa/rag/services/api-gateway/cmd/main.go)
- [services/api-gateway/internal](/mnt/deepa/rag/services/api-gateway/internal)

### High-value tests

- auth failure behavior
- tenant-context propagation
- route-to-service mapping correctness
- rate-limit and body-limit behavior
- correlation ID propagation
- error mapping consistency

## 3.3 Inference Service

Relevant areas:

- [services/inference-svc/app](/mnt/deepa/rag/services/inference-svc/app)
- [services/inference-svc/tests](/mnt/deepa/rag/services/inference-svc/tests)

### High-value tests

- prompt and retrieval integration behavior
- MCP or tool-action paths where present
- policy violation behavior
- external model dependency failure behavior
- breaker and degraded behavior
- trace and audit context propagation

## 3.4 Retrieval Service

Relevant areas:

- [services/retrieval-svc/app](/mnt/deepa/rag/services/retrieval-svc/app)
- [services/retrieval-svc/tests](/mnt/deepa/rag/services/retrieval-svc/tests)

### High-value tests

- vector and graph retrieval composition
- pre-retrieval filtering
- post-retrieval reranking or merging
- timeout and dependency failure behavior
- retrieval-quality regression
- tenant isolation in retrieval paths

## 3.5 Ingestion Service

Relevant areas:

- [services/ingestion-svc/app](/mnt/deepa/rag/services/ingestion-svc/app)
- [services/ingestion-svc/tests](/mnt/deepa/rag/services/ingestion-svc/tests)

### High-value tests

- parsing and chunking
- embedding path behavior
- indexing correctness
- malformed or oversized input handling
- ingestion status transitions
- metadata and tenant propagation

## 3.6 Evaluation Service

Relevant areas:

- [services/evaluation-svc/app](/mnt/deepa/rag/services/evaluation-svc/app)
- [services/evaluation-svc/tests](/mnt/deepa/rag/services/evaluation-svc/tests)

### High-value tests

- offline evaluation logic
- regression gate behavior
- result-scoring correctness
- prompt or retrieval comparison paths
- error handling for missing inputs or malformed runs

## 3.7 Governance, Identity, FinOps, Observability

Relevant areas:

- [services/governance-svc](/mnt/deepa/rag/services/governance-svc)
- [services/identity-svc](/mnt/deepa/rag/services/identity-svc)
- [services/finops-svc](/mnt/deepa/rag/services/finops-svc)
- [services/observability-svc](/mnt/deepa/rag/services/observability-svc)

### High-value tests

- role and scope enforcement
- policy deny paths
- audit correctness
- identity propagation
- budget or cost accounting paths
- observability configuration and alerting logic

## 4. Cross-Cutting Deep Tests

These are the most valuable end-to-end and scenario tests in this repo.

### MCP, drafts, replay

Relevant areas:

- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)
- [mcp/drafts.py](/mnt/deepa/rag/mcp/drafts.py)
- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)

High-value tests:

- downstream outage creates draft
- replay after recovery succeeds
- replay conflict is surfaced safely
- actor attribution is truthful
- audit behavior is present on sensitive actions

### Circuit breaker

Relevant area:

- [libs/py/documind_core/circuit_breaker.py](/mnt/deepa/rag/libs/py/documind_core/circuit_breaker.py)

High-value tests:

- breaker opens after threshold
- fast reject while open
- half-open probe behavior
- recovery closes breaker
- breaker state is surfaced operationally

### RAG quality

High-value tests:

- retrieval regression
- prompt regression
- unsupported answer behavior
- source and citation behavior where applicable
- PII and guardrail paths

## 5. Error Classes To Cover Explicitly

### Browser and UI

- console error
- hydration error
- chunk-load error
- failed API call
- bad empty state

### API

- `400`
- `401`
- `403`
- `404`
- `409`
- `422`
- `429`
- `500`
- `502` or `503`

### Routing

- broken frontend route
- bad gateway route
- bad namespace or tool route
- lost tenant or auth context

### Dependency and resilience

- timeout
- retry exhaustion
- breaker open
- degraded fallback
- replay after recovery

## 6. Recommended Deep Testing Sequence

1. run current lint and unit test surfaces
2. validate service-specific integration tests
3. validate frontend browser and F12 behavior on core pages
4. run MCP, breaker, and replay scenarios
5. validate AI quality and guardrail scenarios
6. validate governance and identity denials
7. validate operator-facing debugging and error visibility

## 7. Strong Next Improvements For The Repo

- add explicit frontend tests for failed API and error-state rendering
- add contract tests for gateway and error envelopes
- add drill-style tests that prove replay truthfulness
- add browser-based end-to-end coverage for core pages
- convert recent production or manual bugs into regression tests
- make operator debugability part of test acceptance criteria

## 8. Bottom Line

The repo already has a real testing base:

- Python pytest coverage
- Go test coverage
- frontend vitest surface
- CI enforcement

The highest-value next move is not “more tests” in the abstract.
It is deeper testing of:

- error behavior
- browser-visible failures
- degraded and replay paths
- routing and tenant correctness
- governance and audit truthfulness
