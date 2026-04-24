# Changelog

All notable changes use [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

### Added (remediation pass — 2026-04-23)
- Dockerfiles for every service: 4 Python + 5 Go + frontend (Next.js standalone).
- `.github/workflows/ci.yml` — Python lint + type + test + security, Go build + vet + test per-service, frontend build, Docker build (no push), K8s YAML validation.
- `.pre-commit-config.yaml` — ruff + black + mypy + detect-secrets + gofmt + golangci-lint + pre-commit hooks.
- `pyproject.toml` — ruff, black, mypy, pytest, coverage config centralized.
- `CHANGELOG.md` — this file.
- `CODEOWNERS`, `.github/pull_request_template.md`.
- `docs/AUDIT-2026-04-23.md` — honest audit of what's real vs scaffolded.
- Outbox pattern — `ingestion.outbox` table + drain worker publishes Kafka events atomically with saga writes.
- Kafka wired into saga: `document.lifecycle.v1` events published via outbox on every step completion.
- Real RS256 JWT minting in identity-svc (Go) with bcrypt password hashing + refresh flow + deny-list for revocation.
- DB-backed prompt registry replacing the in-memory dict in inference-svc; falls back to built-in templates if DB unreachable.
- Retrieval-poisoning defense: `PromptInjectionDetector` + `PIIScanner` now run against INGESTED chunks before indexing, not just on output.
- Re-embed worker for embedding-model swaps (ingestion-svc startup + cron).
- Full saga compensations in recovery worker — runs `QdrantRepo.delete_document` + `Neo4jRepo.delete_document` + `ChunkRepo.delete_by_document` + blob delete.
- 50-item synthetic eval dataset under `data/eval/v1/`.
- Grafana dashboards JSON (service-overview, SLO burn, cost, retrieval quality).
- Integration tests via FastAPI `TestClient` with mocked externals (Ollama, Qdrant, Neo4j).
- Cross-tenant isolation test (skipped if no `DOCUMIND_PG_HOST`).

### Fixed
- Inflated implementation counts in `docs/design-areas/table/00-INDEX.md` — now honest (25 ✅ / 28 🟡 / 14 ❌).
- Rate-limiter default on admin paths is now **fail-closed**, not fail-open.
- Python stubs in `observability.py` E301 blank-line fix (earlier).
- Inline dataclass in `rag_inference.py` E301 blank-line fix (earlier).

## [0.1.0] — 2026-04-23

Initial scaffold: 67-area DocuMind RAG platform, class-based throughout,
with shared `documind_core` Python lib (exceptions, config, logging,
middleware, circuit breakers, ai_governance), 4 Python services
(ingestion, retrieval, inference, evaluation), 5 Go service skeletons
(api-gateway, identity, governance, finops, observability), Next.js +
vanilla CSS frontend, Docker Compose, Istio + K8s manifests, ELK +
Kiali, vLLM GPU variant, AIops alerts, and reference tables for all 67
design areas + 7 cross-cutting extras.
