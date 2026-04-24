# Changelog

All notable changes use [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased] — 2026-04-23 remediation pass (honest)

### Added

- **Dockerfiles** for every service: 4 Python (multi-stage, non-root) + 5 Go (multi-stage, static) + frontend (Next.js standalone). Not yet built in this session.
- **`.github/workflows/ci.yml`** — Python lint + type + test + security, Go build + vet + test per-service matrix, frontend build, Docker build (no push) for all 10 images, K8s YAML validation with kubeconform + yamllint. Not yet run.
- **`.pre-commit-config.yaml`** — ruff + black + mypy + detect-secrets + gofmt + golangci-lint + stock hooks.
- **`pyproject.toml`** — ruff / black / mypy / pytest / coverage / bandit config centralised.
- **`CHANGELOG.md`** — this file.
- **`.github/CODEOWNERS`** + **`.github/pull_request_template.md`**.
- **`docs/AUDIT-2026-04-23.md`** — honest audit of what's real vs scaffolded.
- **Outbox pattern** — `ingestion.outbox` table + `OutboxRepo.enqueue(conn, ...)` that accepts a caller-provided connection so the INSERT is atomic with the caller's domain write (bug fixed in second sub-commit).
- **Kafka wired into saga** — at end-of-saga, state transition INDEXED→ACTIVE and the `document.indexed.v1` outbox row are in the SAME `tenant_connection` transaction.
- **`services/identity-svc/internal/jwt/jwt.go`** — RS256 Issuer with `Mint/Verify/Revoke`, Redis-backed `Denylist` interface (dev `NoopDenylist` clearly marked). **Password hashing NOT yet wired** (the Go service has no handlers yet).
- **DB-backed prompt registry** — `DbBackedPromptBuilder` polls `governance.prompts` every 30s; falls back to built-in templates on cold start / DB outage.
- **Retrieval-poisoning defense** — `ChunkPoisoningGuard` runs `PromptInjectionDetector` + `PIIScanner` against ingested chunks BEFORE indexing. Wired into saga's chunk step.
- **Re-embed worker** — `ReembedWorker` scans chunks whose `metadata.embedding_model` differs from current; re-embeds in batches with `SKIP LOCKED`. Saga's embed step now stamps `embedding_model` on chunks so the worker doesn't re-pick just-embedded chunks (bug #3 fix).
- **Recovery worker** now runs REAL per-step compensations (Qdrant → Neo4j → chunks → blob) in reverse order, not just mark-failed.
- **50-item synthetic eval dataset** at `data/eval/v1/rag_qa.jsonl`. Clearly labeled synthetic — `expected_chunk_ids` are placeholders, NOT corpus-linked, so retrieval metrics from this dataset are NOT meaningful (see `data/eval/v1/README.md`). Answer-relevance / faithfulness metrics still work.
- **Grafana dashboard** — `documind-overview.json`. References ONLY metrics emitted by `libs/py/documind_core` and `services/ingestion-svc`. The previously-shipped `slo-burn.json` was removed because every panel referenced metrics that don't have producers (see `infra/observability/grafana-dashboards/README.md` for the explicit retraction).
- **Unit tests** — 8 new tests in `libs/py/tests/test_ai_governance.py`, 7 in `services/ingestion-svc/tests/test_poisoning_defense.py` (including 3 false-positive regression tests for bug #2), 3 in `services/inference-svc/tests/test_integration_inference.py` (mock-based orchestration verification — NOT TestClient end-to-end).
- **RLS cross-tenant test scaffold** — the earlier one is removed because it couldn't run without live Postgres + migrations already applied, and the skip conditions masked that. A proper version needs a `docker compose up postgres` + migration step in CI.

### Fixed

- **Bug #1 (CRITICAL, own-find, fixed in this pass)** — previous outbox implementation opened its own `tenant_connection`, defeating atomicity. Fixed by threading the caller's `conn` through.
- **Bug #6 (own-find, fixed)** — `DocumentIngestionSaga` accessed `_document_repo._db` (private attr). Now takes `db: DbClient` as a constructor arg. Service wiring updated.
- **Bug #2 (own-find, fixed)** — injection regex matched common prose like "don't forget to pack an umbrella" or "subclass should override". Tightened to require both a verb AND a jailbreak-object word (instructions / prompts / rules / policy / messages). Added 3 false-positive regression tests.
- **Bug #3 (own-find, fixed)** — re-embed worker would re-embed every chunk forever because `embedding_model` wasn't stamped on chunks during the saga's embed step. Added `ChunkRepo.stamp_embedding_model` called at embed completion.
- **Inflated `00-INDEX.md` counts** — reset from `49 ✅` to the honest `~31 ✅ / ~24 🟡 / ~12 ❌`.

### Corrected from earlier drafts of this CHANGELOG (caught on re-read)

- Removed the claim that a `requirements.lock` was added — it wasn't. Adding it requires `pip-compile` per service; deferred.
- Removed the claim of "bcrypt password hashing" in identity-svc — the Go JWT issuer exists but login/password flow isn't yet coded.
- Removed the claim that rate-limit defaults were changed to fail-closed on admin paths — that change wasn't actually made to code this session.
- Corrected the dashboard list — only `documind-overview.json` is shipped; `slo-burn.json` / `cost.json` / `retrieval-quality.json` were never written.
- Corrected integration-test description — uses `unittest.mock.AsyncMock`, not FastAPI `TestClient`. Orchestration verification, not request/response E2E.

## [0.1.0] — 2026-04-23

Initial scaffold: 67-area DocuMind RAG platform, class-based throughout, with shared `documind_core` Python lib (exceptions, config, logging, middleware, circuit breakers, ai_governance), 4 Python services (ingestion, retrieval, inference, evaluation), 5 Go service skeletons (api-gateway, identity, governance, finops, observability), Next.js + vanilla CSS frontend, Docker Compose for data stores + observability, Istio + K8s manifests, ELK + Kiali, vLLM GPU variant, AIops alert rules, and reference tables for all 67 design areas + 7 cross-cutting extras.
