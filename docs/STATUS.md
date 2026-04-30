# circuitRAG / DocuMind — Status & Architecture (current)

> Single canonical "what's actually shipped vs. PLANNED" document.
> Updated: 2026-04-30 (commit `80dec99`+).
>
> Every statement here is verifiable against the repo. Drills lock
> the most-load-bearing claims (see "What's tested" section).

## TL;DR

| Surface | State |
| --- | --- |
| **Local-model issue dispatcher mechanism** (scanner → council → review → apply → audit) | ✅ shipped end-to-end |
| **CI strict gates** (ruff / mypy / bandit / pytest) | ✅ all hard-gated |
| **Edge stack** (NGINX + api-gateway + CDN cache contract) | ✅ shipped + drilled |
| **Observability core** (OTel, Prometheus, Grafana, Jaeger) | ✅ in compose |
| **LLM observability** (Langfuse) | ✅ shipped (opt-in profile) |
| **Mesh path** (Istio + Kiali via minikube) | ✅ scripts shipped; operator runs |
| **Deep-dive catalog** (28+ pages under /admin/*/deep) | ✅ shipped |
| **5-phase k6 load test** | ✅ shipped (this commit) |
| **Vectorless retrieval (ES)** | ⚠ wrapper shipped; ingestion + integration not wired |
| **Production deployment** (k8s + real mesh) | ❌ not in scope; minikube path only |

## Architecture (high-level)

```
                               ┌─────────────────────┐
                               │  Browser            │
                               │  (Next.js client)   │
                               └──────────┬──────────┘
                                          │ HTTPS
                                          ▼
                                 ┌────────────────┐    Cache contract:
                                 │  NGINX         │    /api/* = no-store
                                 │  (TLS + cache) │    /_next/static = 7d
                                 └────────┬───────┘
                                          │ HTTP/2
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                ┌───────────────────┐           ┌────────────────┐
                │  api-gateway      │           │  Next.js BFF   │
                │  (Go)             │           │  (SSR + API)   │
                │  JWT + rate-limit │           │  /api/v1/*     │
                │  + correlation_id │           └────────┬───────┘
                └────────┬──────────┘                    │
                         │  mTLS (when mesh active)      │
                         └──────┬────────┬───────────────┘
                                ▼        ▼        ▼
                  ┌─────────────────┐ ┌──────────────────┐
                  │ sidecar-advisor │ │ agent-orchestr.  │
                  │ FastAPI + SQLite│ │ FastAPI + LangGr │
                  │ council pattern │ │ + Postgres state │
                  └────┬────────────┘ └────────┬─────────┘
                       │                       │
                       ▼                       ▼
                 ┌───────────┐  ┌───────────┐  ┌────────────┐
                 │ inference │  │ retrieval │  │  Ollama    │
                 │ FastAPI   │  │ FastAPI   │  │  (local)   │
                 └───┬───────┘  └────┬──────┘  └────────────┘
                     │               │
                     ▼               │
              ┌──────────┐    ┌──────┴───────┬───────────┐
              │ Postgres │    │   Qdrant     │   Neo4j   │
              │ (RLS)    │    │  (vector)    │  (graph)  │
              └──────────┘    └──────────────┴───────────┘

       Cross-cutting (in compose):
         Redis (cache, rate-limit, idempotency)
         Kafka + Zookeeper (event backbone)
         MinIO (S3-compatible blob store)
         OTel collector + Prometheus + Grafana + Jaeger
         Elasticsearch + Kibana + Filebeat (log aggregation)
         Langfuse (LLM observability — opt-in profile)
         api-gateway, kiali (opt-in profiles)
```

Detailed C4 diagrams: `docs/architecture/C4-{context,container,component,agentic}.md`.

## What's working (verified, drill-locked)

### Tooling
- **ruff**: 0 errors. Hard-gated in CI. Floor locked by `drill_issue_dispatcher_format.py`.
- **mypy**: 0 errors. Hard-gated in CI since `39f52ae`. Floor locked by `drill_ci_strict_gates.py`.
- **bandit**: scanner integrated; all S-rules route to `human-review` per §50.5; locked by drill.
- **eslint**: scanner integrated; 23 issues currently in queue (22 medium + 1 autofix).
- **drill catalog**: 100+ readonly drills under `mcp/tests/`. Run via `scripts/run_drills.py`.

### Core platform code
- **Circuit breakers** (5 specialized): generic, retrieval-quality, cognitive, token, agent. Drills lock state-machine + Prometheus metrics.
- **JWT validation**: api-gateway (Go) does JWKS-cached RS256. ADR-006 + drill_jwt_strict_claim_validation.
- **PII redaction**: `documind_core.observability` redacts before logs/audit. drill_pii_redaction.
- **Idempotency middleware**: Redis + Postgres-backed. drill_idempotency_postgres_protocol_seam.
- **Audit log**: append-only Postgres partitioned per global §38. governance-svc owns schema.
- **OTel baggage propagation**: tenant_id + correlation_id flow across every hop. drill_baggage_propagation.

### Local-model mechanism (shipped this session)
- **Issue scanner** (`scripts/issue_scanner.py`): ruff + mypy + bandit + eslint signal sources.
- **Council dispatcher** (`scripts/issue_dispatcher.py`): 3-model (author + reviewer + advisor) sequential council.
- **Review tool** (`scripts/review_council.py`): dedupes audit log, persists decisions.
- **Experts registry** (`scripts/experts.py`): 6 named local-model specialists (code/doc/review/advise/layer/gpt).
- **Operator UI** at `/admin/local-models` — live view of installed + loaded models, recent council runs.
- Globally lifted to `~/.claude/scripts/` with `--repo` portability.

### Edge + observability
- **NGINX**: TLS termination + per-route cache contract (`Cache-Control: no-store, private` on /api/). Drill: `drill_cdn_cache_invariants`.
- **api-gateway**: opt-in compose profile (`--profile app`); upstream falls back to host-native gateway via `backup` keyword.
- **OTel collector**: receives traces/metrics/logs from every service.
- **Prometheus + Grafana**: scrape + dashboard. 1 dashboard committed (documind-overview.json); 4 ratchet dashboards as drills.
- **Langfuse**: opt-in (`--profile observability`) for per-LLM-call traces with prompt + completion + cost.

## What's NOT working (honest)

### PLANNED — wrappers exist, integration doesn't
- **Vectorless retrieval (ES)**: `services/retrieval-svc/app/services/elastic_searcher.py` wrapper class exists with tenant-isolation contract. NOT wired into `HybridRetriever`. NO ingestion pipeline writes documents to ES. ES is currently log-aggregation only (Filebeat + Kibana).
- **Knowledge graph build**: `infra/istio/` YAMLs reference a graph-svc but no service code exists. `/admin/knowledge-graph/deep` documents the ontology+graph design as PLANNED.
- **LLM incident summarizer**: `/admin/aiops/deep#llm-incident-summarization` documents the design; no code shipped.
- **Dedicated NGINX + Go gateway tier as default**: api-gateway code shipped + opt-in via profile. Default is BFF-as-gateway.
- **Eval harness golden set**: `evaluation-svc` has REST API for scoring; no formal golden set committed.

### Operator-only blockers (cannot fix from autonomous loop)
- **Real CDN provider** (Cloudflare / Fastly / CloudFront credentials)
- **Real `ALERTMANAGER_WEBHOOK_URL`** (Slack/Discord/PagerDuty admin)
- **Real `COUNCIL_STATS_WEBHOOK`** (same)
- **Parallel-tool drill template upstream fix** (out-of-band coordination)
- **Ollama systemd `id_ed25519` permission fix** for cloud-model pulls (`sudo chown ollama:ollama /usr/share/ollama/.ollama`)

## Challenges / risks

1. **Multi-tenant isolation in retrieval**: Qdrant + Neo4j + ES all rely on `tenant_id` filter at query layer. Drills lock the filter on every searcher. ES wrapper just shipped this iteration locks the same contract. Risk: a future code path that bypasses the searcher class.
2. **Convergent work with parallel-tool**: ADR-022 documents 4 cases of parallel-tool + autonomous-loop both producing the same artifact. Risk is wasted work, not correctness — drill catalog catches drift.
3. **Local-model proposal correctness**: empirically the single-model lane proposed wrong fixes (E402 = REMOVE vs RELOCATE). 3-model council with diverse lineages caught it. Risk: edge-case rules where all 3 models share the same misconception.
4. **Compose vs natively-run philosophy split**: `docker-compose.yml` header says "infra-only"; api-gateway + langfuse opt-in via profiles. Risk: drift toward containerizing-by-default loses the fast-rebuild dev path.
5. **CI runs ruff/mypy/bandit/pytest hard-gated** but doesn't run the drill catalog. Drills are enforced by the LoopWatcher pre-commit hook + manual `scripts/run_drills.py`. Risk: a PR that disables a drill won't fail CI.
6. **Ollama is single-machine**: all council work routes through localhost:11434. Risk: machine death = no council work. Cloud fallback (chair-fallback `6831dee`) exists but is single-tier.
7. **Postgres single-instance**: no read replicas; no automatic failover. Phase-1 acceptable; production needs HA.

## Testing strategy

| Category | Where | Status |
| --- | --- | --- |
| Unit (Python) | `libs/py/tests/`, `services/*/tests/` | run by CI pytest |
| Type (mypy) | `libs/py/documind_core/` | hard-gated CI |
| Lint (ruff) | `libs/py/`, `services/` | hard-gated CI; 0 errors |
| Security (bandit) | `services/` | hard-gated CI |
| Integration (drills) | `mcp/tests/drill_*.py` | 100+ readonly + a few non-readonly; run via `scripts/run_drills.py` |
| Council regression | `.loop/issue_audit.jsonl` | dedup'd via `scripts/review_council.py`; 13+ council audit rows |
| Frontend (Vitest) | `services/frontend/tests/` | 1 file (sidecar-rating-route); minimal |
| E2E (Playwright) | none | gap; documented in /admin/deep-dives |
| **Load (k6)** | `infra/load-test/k6/baseline.js` | **shipped this iteration; 5 phases** |

## Benchmarking

### How to run
```bash
# Sanity smoke (15 seconds)
bash scripts/load-test.sh smoke

# Production-readiness gate (22 min — runs all 5 phases)
bash scripts/load-test.sh full

# Specific phase
bash scripts/load-test.sh stress
```

### What it tests
| Hot path | Endpoint | k6 tag |
| --- | --- | --- |
| Health probe | `GET /healthz` | `health` |
| Sidecar event submit | `POST /api/v1/sidecar/events` | `api` |

### SLO thresholds enforced
- `/healthz` p95 < 100ms
- `/api/*` p95 < 500ms
- error rate < 1%

### Scaling targets

| Target VU | Where to run |
| --- | --- |
| 10 — 1k | Single laptop / `scripts/load-test.sh stress` |
| 1k — 10k | Single beefy VM with kernel tuning (FDs, conntrack) |
| 10k — 100k | k6 Cloud OR multi-machine k6 workers |
| 100k+ | k6 Cloud regional or distributed gen-cluster |

The k6 script is configuration-as-code — same file, different runners. `BASE_URL` + `AUTH_BEARER` env vars cover environment portability.

## Agent monitoring

Live operator views:

- `/admin/local-models` — installed Ollama models, currently loaded, recent council runs (audit chain), checklist breakdown
- `/admin/agentic` — agent-orchestrator plan + memory state
- `/admin/agentic/control-plane` — orchestrator control-plane data
- `/admin/sidecar` — sidecar advisor event history with ratings
- `/admin/forensics` — correlation_id-led incident triage

Audit trails (`.loop/`):
- `issue_audit.jsonl` — every model invocation (lane, model, tokens, latency)
- `issue_decisions.jsonl` — operator's per-issue decision (apply / skip / reject + note)
- `council_batch_summary.json` — last batch run summary
- `experts_log.jsonl` — every experts.py invocation
- `last_drill_outcome.json` — drill catalog state for LoopWatcher
- `watcher.log` — LoopWatcher REJECT / APPROVE history

## Where to look for what

| Question | File |
| --- | --- |
| What does this project do? | this file (`docs/STATUS.md`) |
| How is it structured? | `docs/architecture/C4-context.md` + 3 sibling C4 files |
| Why this design choice? | `docs/architecture/adr/*.md` (22+ ADRs) |
| How do I run X? | `docs/runbooks/<topic>.md` |
| What's tested how? | `mcp/tests/drill_*.py` + this file's "Testing strategy" |
| Dev workflow rules | `~/.claude/CLAUDE.md` (50+ sections of policy) |
| What's currently broken? | this file's "What's NOT working" section |
| How do I load-test? | `infra/load-test/README.md` |

## Composes with

- `~/.claude/CLAUDE.md` §50 — global local-model dispatcher policy that this repo's mechanism implements
- `docs/runbooks/*.md` — per-runbook operator paths (alertmanager-webhook, cdn-integration, istio-local-deploy, langfuse, issue-dispatcher)
- `docs/architecture/adr/*.md` — every locked architectural decision
- `mcp/tests/drill_*.py` — every regression contract

## Brutal rule

> A repo without a STATUS doc that's verifiable against the codebase
> ages into "tribal knowledge" within months. This file is the
> one canonical answer to "what's working / what's not / what's next".
> Update it on every architectural change. Drift between this file
> and reality is itself a defect.
