# Changelog

All notable changes use [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased] — 2026-04-27/28 baggage + forensics + CI push

A coordinated 26-commit push spanning four arcs: deep-dive page
expansion, baggage/forensics observability surface, audit log
partitioning, and CI drill-suite gating. Composes with the
§38 / §47 / §48 architecture policies in `~/.claude/CLAUDE.md` +
the §43 drill discipline.

### Added — Architecture deep-dive surface

- 14 new deep-dive pages under `services/frontend/app/admin/<topic>/deep`:
  `c4-model` (7 levels, AI-extended), `adr` (decision-record
  fundamentals + 10-ADR catalog), `jad` (JAD → BRD → C4 → ADR chain),
  `voice-ai` (speaker recognition evolution), `security` (OWASP 2025
  + STRIDE + DevSecOps + SOC2), `rollout` (4-layer rollback + K8s
  3-probe), `principles` (SOLID + 17-factor + KISS/YAGNI/DRY),
  `load-testing` (k6 + JMeter + RAG layered), `cicd` (master pipeline
  + TDD + AI eval), `post-release` (deployment playbook + PDV +
  rollback decision matrix), `checklist` (production-readiness master
  gate, 17 sections + 6 hard stops), `explainability` (XAI + SHAP /
  LIME / counterfactual + audit row schema + RAG four-part contract),
  `tracing` (W3C baggage + trace → draft → audit linkage),
  `forensics` (operator UI for trace lookup).
- New `DeepDiveCrossRefs` component
  (`services/frontend/components/DeepDiveCrossRefs.tsx`) rendering a
  "Composes with" footer per §49 of `~/.claude/CLAUDE.md`. Adopted on
  **all 32/32** deep-dive pages — every page now declares 3–7
  outbound dependencies with one-sentence WHY.
- TTS / speech reader features (sentence-by-sentence highlighting,
  word-level overlay, voice picker, speed presets including 1.25×,
  en-US voice filter, arithmetic-symbol strip, plural-aware
  pronunciation dictionary).
- Sidebar reorganized into per-topic anchor groups so each scenario
  is a one-click destination.

### Added — Baggage / forensics observability (10-commit feature surface)

End-to-end W3C trace context + baggage propagation across HTTP +
Kafka + logs, plus operator-facing forensics endpoint and UI. Drilled
at **34/34 steps green** across 5 drill files.

- **`mcp/server_common.py`** — `setup_server_otel()` now wires
  `CompositePropagator(TraceContext + W3CBaggage)` globally + auto-
  instruments `httpx` outbound. New helpers: `baggage_set`,
  `baggage_get`, `baggage_get_all`, `inject_propagation_headers`,
  `extract_propagation_context`. The default OTel propagator is
  tracecontext-only — without this, the baggage header is never
  emitted.
- **`libs/py/documind_core/middleware.py`** — new
  `BaggageContextMiddleware` promotes `request.state.tenant_id /
  user_id / correlation_id` (already populated by
  `TenantContextMiddleware`) into W3C baggage so outbound httpx
  calls auto-carry them downstream. Wired into all 4 Python services
  (inference, retrieval, ingestion, evaluation).
- **`libs/py/documind_core/logging_config.py`** — new structlog
  processor `_inject_baggage` adds every baggage entry to every JSON
  log record. Composes with existing `_inject_context` (contextvar
  injection) and `_inject_otel_trace` (trace_id + span_id). Collision
  policy: explicit kwargs > contextvar > baggage; documented +
  drilled.
- **`libs/py/documind_core/kafka_client.py`** — `EventProducer.publish`
  appends `traceparent` + `baggage` headers to every Kafka message;
  `IdempotentConsumer._handle_one` extracts on receive + attaches
  OTel context for the handler's lifetime + detaches in `finally`
  (multi-tenant consumer poll-loop isolation).
- **`services/inference-svc/app/routers/__init__.py`** —
  `/api/v1/admin/trace/{correlation_id}` extended to join
  `governance.hitl_queue` alongside `audit_log` + `action_drafts`.
  Forensics now covers all 3 governance tables + Jaeger deep-link.
- **`services/inference-svc/app/schemas/__init__.py`** —
  `TraceLinkHitlRow` + `hitl_rows` field on `TraceLinkResponse`.
  `ClientErrorRecord` gains `tenant_id` field, populated server-side
  from `request.state.tenant_id`.
- **`services/frontend/app/admin/forensics/page.tsx`** — new operator
  UI consuming `/api/v1/admin/trace/{cid}`. Form-based input + summary
  card + audit/drafts/HITL tables + Jaeger deep-link button. Accepts
  `?correlation_id=...&tenant_id=...` query params and **auto-fires
  the lookup** on landing when both UUIDs validate. URL stays in sync
  via `replaceState` for shareable deep-links.
- Deep-link integration on caller pages: `/admin/client-errors` (each
  error row's correlation_id is now a `<Link>` to forensics with
  cid + tid pre-filled) and `/admin` dashboard (inline trace form
  renders HITL rows + offers an "Open in Forensics →" link).

Drill files (in `mcp/tests/`):

- `drill_baggage_propagation.py` — 8 steps, 3 negative assertions
  (W3C contract: extract required, percent-encoding, child-context
  isolation).
- `drill_baggage_middleware.py` — 6 steps, 3 negative assertions
  (no-default invention, OTel-missing degradation, PII keys not
  auto-promoted).
- `drill_baggage_log_formatter.py` — 6 steps, 4 negative assertions
  (collision policy locked).
- `drill_baggage_kafka.py` — 6 steps, 3 negative assertions (None
  headers, non-UTF-8 skip, post-detach context isolation).
- `drill_inference_trace_link.py` extended from 7 → 9 steps with
  HITL join + cross-cid bleed negative.

### Added — Audit log partitioning

- **`services/governance-svc/migrations/009_audit_log_partitioned.sql`**
  — additive sibling table `governance.audit_log_partitioned`,
  declarative-partitioned by RANGE (timestamp). Composite PK
  `(id, timestamp)` per Postgres requirement. RLS + indexes
  propagate to partitions. Bootstrap creates 3 monthly partitions
  (current + next 2). Helper plpgsql function
  `governance.create_audit_log_partition(yyyy, mm)` is idempotent +
  handles December → January year rollover correctly. Drilled at
  **8/8 steps green** including 3 negative assertions
  (`drill_audit_log_partitioned.py`).
- **`docs/ops/audit-log-partitioned-cutover.md`** — 5-phase
  operations runbook with explicit SQL per phase + verification +
  reversibility notes + sign-off checklist. Phase 5's `DROP TABLE`
  is the first irreversible step in the entire flow + tagged as
  such.

### Added — CI drill-suite gating

- **`.github/workflows/drills.yml`** — two PR-time jobs:
  - `drills-fast` — 15 zero-infra drills, ~10s wall, every PR.
  - `drills-pg` — 23 drills (15 fast + 8 PG-specific) with
    `postgres:16-alpine` service container + migrations applied;
    runs as non-BYPASSRLS `documind_app` for honest RLS verification.
- **`.github/workflows/drills-stack.yml`** — schedule-only (01:00
  UTC) + `workflow_dispatch`. Brings up MCP HR via `setsid python -m
  mcp.server_hr`, polls `/health` (60s deadline), runs 29 drills
  (`--allow-resources=pg,mcp_hr`).
- Both workflows on nightly schedule (`drills.yml` at 00:30 UTC,
  `drills-stack.yml` at 01:00 UTC) for drift-detection — catches
  dep / image / OTel / structlog updates that would otherwise land
  silently between PRs.
- **`scripts/run_drills.py`** — new `--allow-resources` filter for
  tier selection. Empty string = filter active with empty allow-list
  = zero-infra drills only. `None` = no filter (all drills run).
- 18 drills retagged for honest tier classification: 14
  `frontend_*` from `none` → `frontend`, 4 playwright-using drills
  from `readonly` → `playwright`. Tier 1 count moved from 33 → 15
  (false-positives removed).
- **`docs/ci-drills-setup.md`** — 7-section runbook for repo admin:
  tier definitions table, required-status-checks list, drill-author
  checklist, failure-debugging guide, nightly rationale, progressive
  tier rollout (3a shipped; 3b/3c deferred), one-time setup
  checklist.

### Added — Global policies (`~/.claude/policies/`)

- `architecture-design-patterns.md` — 7 design surfaces (C4 + ADR +
  JAD + Security + Rollout + Principles + Load Testing) covering
  AI-extended C4 (L5 Governance / L6 Observability / L7 Lifecycle),
  10-ADR AI-SDLC catalog, OWASP 2025 + STRIDE + DevSecOps + SOC2,
  4-layer rollback + 3-probe pattern, 17-factor, 5-phase load
  testing.
- `ai-explainability.md` — global vs local XAI, SHAP / LIME /
  counterfactual, model card schema, decision audit row schema, RAG
  four-part contract, agent tool-call audit, EU AI Act / NIST RMF /
  ISO 42001 mapping. Materialized in `/admin/explainability/deep`.

`~/.claude/CLAUDE.md` extended with §47 (architecture-design-patterns
reference), §48 (ai-explainability reference), §49 (compose-footer
mandate + audit query).

### Migration

This release is **fully backward compatible**. The audit-log
partitioning is additive — legacy `governance.audit_log` is
unchanged. The 5-phase cutover runbook in
`docs/ops/audit-log-partitioned-cutover.md` is when ops decides to
flip. No code change blocks deploy.

### Coverage summary

- Deep-dive pages: **32/32** with compose-footer (100%).
- Drill suite: **83 total**. CI-gated today: 15 (tier 1) + 23 (tier 2)
  per PR; +29 (tier 3a) nightly. Deferred: 54 (tier 3b/3c, runbook
  documents progressive rollout).
- Baggage drills: **34/34** steps green across 5 drill files.
- Cross-link verification: every footer reference points to an
  existing page (no aspirational links). Audit query in
  `~/.claude/CLAUDE.md` §49.4 returns zero MISSING entries.

### Next-iteration follow-ups (queued)

- Tier 3b CI workflow (drills-stack-inference, +40 drills, ~8 min)
  — inference-svc dependency tree.
- Tier 3c CI workflow (drills-stack-full, +20 drills, ~15 min) —
  frontend / Playwright / Qdrant / Kafka.
- Branch-protection setting flip on `main` + `develop` — admin
  action via GitHub Settings; `docs/ci-drills-setup.md` lists exact
  check names.
- Operations cutover execution for `audit-log-partitioned` (when
  ops decides) — runbook is the procedure.

---

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
