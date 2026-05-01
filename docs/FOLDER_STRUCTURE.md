# Folder Structure

> §19 mandate. The live tree is the source of truth — run `tree` or
> `find . -maxdepth 3 -type d` for the current view.
>
> See: [`PROJECT_STANDARDS.md`](PROJECT_STANDARDS.md) — naming + ADR conventions
> See: [`TECHSTACK.md`](TECHSTACK.md) — what each service is built on
> See: [`architecture/HLD-documind.md`](architecture/HLD-documind.md) — high-level service boundaries

## Top-level

```
.
├── data/                  Stateful test fixtures + transient data
├── docs/                  All documentation (this file lives here)
│   ├── architecture/      ADRs (under adr/), C4 diagrams, design docs
│   ├── DEMO-*.md          Demo / how-to-run artifacts per feature
│   ├── runbooks/          Operator runbooks
│   └── policies/          Project-local policies (overlay on global CLAUDE.md)
├── infra/                 Infrastructure-as-code (compose, k8s, observability)
│   └── observability/     Prometheus + Grafana + alertmanager configs
├── libs/                  Shared libraries
│   └── py/documind_core/  Python shared lib (config, auth, observability, etc.)
├── mcp/                   MCP servers + drills
│   ├── server_*.py        MCP servers (drill, retrieval, etc.)
│   └── tests/drill_*.py   210+ drills (real-stack tests)
├── proto/                 gRPC .proto definitions
├── schemas/               Cross-service JSON schemas
├── scripts/               Operator + maintenance scripts
│   ├── run_drills.py      Resource-aware parallel drill runner
│   └── issue_*.py         Lint/issue dispatcher tooling (§50)
├── services/              All deployable services
│   ├── api-gateway/       Go — edge service
│   ├── inference-svc/     Python — RAG inference
│   ├── retrieval-svc/     Python — vector + graph retrieval
│   ├── ingestion-svc/     Python — document ingestion
│   ├── evaluation-svc/    Python — quality eval + §48 explain
│   ├── agent-orchestrator-svc/  Python — agentic workflow
│   ├── governance-svc/    Go — policy engine + HITL
│   ├── identity-svc/      Go — auth + tenant management
│   ├── observability-svc/ Go — SLO + capacity tracking
│   ├── finops-svc/        Go — token cost + budgets
│   ├── frontend/          Next.js 14 — admin UI + dashboards
│   └── sidecar-advisor/   Python — sidecar review
├── tests/                 Cross-cutting test fixtures (per-svc lives in svc/tests/)
└── workflows/             Workflow / agent definitions
```

## Per-service structure (Python pattern)

```
services/<svc>/
├── app/
│   ├── core/              Service-specific config + lifespan
│   ├── routers/           HTTP route handlers (or inline in main.py)
│   ├── schemas/           Pydantic request/response models
│   ├── services/          Business logic (class-based, DI)
│   ├── workers/           Background workers (Kafka consumers, etc.)
│   └── main.py            FastAPI app factory
├── tests/                 pytest unit + integration
├── migrations/            Numbered SQL migrations (if owns a DB)
├── Dockerfile
└── pyproject.toml         (or shared via root)
```

## Per-service structure (Go pattern)

```
services/<svc>/
├── cmd/                   main.go + main_test.go
├── internal/              Per-package handlers, repositories, services
│   ├── handler/
│   ├── repository/
│   └── service/
├── migrations/            Numbered SQL migrations
├── go.mod
├── go.sum
└── Dockerfile
```

## Adding a new service

1. Create `services/<name>/` following the language pattern above
2. Add Dockerfile + at least one test file
3. Wire into `docker-compose.yml`
4. Add an ADR if architecture-shaping
5. Add a deep-dive page at `services/frontend/app/admin/<topic>/deep/page.tsx`
   with `<DeepDiveCrossRefs>` footer (§49)
