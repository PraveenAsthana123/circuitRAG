# C4 L2 — Container Diagram

> One level deeper than L1: shows containers (services/processes) inside
> the DocuMind RAG system.

## Diagram

```mermaid
graph TB
    %% --- People ---
    Analyst[("Risk Analyst")]:::person
    Operator[("Platform Operator")]:::person

    %% --- System boundary ---
    subgraph DocuMind["DocuMind RAG Platform"]

        subgraph FrontendBox["Frontend"]
            Frontend["Next.js 14 (App Router)<br>port 3000<br>/admin/agentic/control-plane<br>/admin/agentic/explain"]:::container
        end

        subgraph ApiBox["API Plane"]
            Orch["agent-orchestrator-svc<br>FastAPI :8087<br>9-stage LangGraph DAG<br>+ §42 hard-stop gates<br>+ §48 explainability"]:::container
        end

        subgraph McpBox["MCP Tool Servers (4 stubs + 3 prod)"]
            Research[("mcp_research :8094<br>research.synthesize<br>(httpx URL fetch)")]:::mcp
            Tests[("mcp_tests :8095<br>ruff/pytest/mypy<br>(real subprocess)")]:::mcp
            Deploy[("mcp_deploy :8096<br>compose_apply/rollback<br>(stub canned)")]:::mcp
            Observe[("mcp_observe :8097<br>prom_query / p95_delta<br>check_alerts_fired")]:::mcp
            Hr[("mcp_hr :8091<br>(prod)")]:::mcp_prod
            Itsm[("mcp_itsm :8092<br>(prod)")]:::mcp_prod
            Drills[("mcp_drills :8093<br>(prod)")]:::mcp_prod
        end

        subgraph DataBox["Data Plane"]
            Postgres[("Postgres :5432<br>orchestration schema:<br>tasks, runs, approvals,<br>memories, deploy_records,<br>observe_windows,<br>tenant_budgets,<br>idempotency_keys,<br>research_artifacts,<br>test_results")]:::data
            Qdrant[("Qdrant :6333<br>100GB vector store")]:::data
        end

        subgraph ObsBox["Observability"]
            Prom[("Prometheus :9090<br>+ Alertmanager :9093")]:::obs
            Grafana[("Grafana :3001<br>dashboards")]:::obs
            Otel[("OTel collector<br>:4317 / :4318")]:::obs
        end

    end

    %% --- External ---
    Ollama[("Local Ollama :11434")]:::ext
    Claude[("Claude CLI binary")]:::ext
    Codex[("Codex CLI binary")]:::ext
    DocSources[("External URLs<br>(http/https)")]:::ext

    %% --- Edges ---
    Analyst -->|"HTTPS"| Frontend
    Operator -->|"HTTPS"| Frontend
    Frontend -->|"REST<br>/api/v1/agentic/*"| Orch

    Orch -->|"agentic graph<br>LLM + MCP calls"| Research
    Orch -->|" "| Tests
    Orch -->|" "| Deploy
    Orch -->|" "| Observe
    Orch -->|"agent tools"| Hr
    Orch -->|" "| Itsm
    Orch -->|" "| Drills

    Orch -->|"tier_a — http"| Ollama
    Orch -->|"tier_b — subprocess"| Claude
    Orch -->|"tier_b — subprocess"| Codex

    Orch -->|"asyncpg<br>(via DbCircuitBreaker)"| Postgres
    Orch -->|"vector queries<br>(retrieval)"| Qdrant

    Research -->|"httpx GET"| DocSources

    Observe -->|"PromQL"| Prom
    Observe -->|"AM v2 API"| Prom

    Orch -->|"prom metrics<br>OTel spans"| Otel
    Otel -->|"scrape"| Prom
    Prom -->|"data source"| Grafana

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef container fill:#438dd5,stroke:#2e6295,color:#fff
    classDef mcp fill:#7caefe,stroke:#5d8fcd,color:#000
    classDef mcp_prod fill:#a3c4f3,stroke:#5d8fcd,color:#000
    classDef data fill:#e8b94e,stroke:#a37e2c,color:#000
    classDef obs fill:#84c08c,stroke:#5d8a64,color:#000
    classDef ext fill:#999999,stroke:#666666,color:#fff
```

## Containers (10 internal + 4 external)

| Container | Tech | Port | Purpose |
|---|---|---|---|
| **Frontend** | Next.js 14 | 3000 | Admin UI: `/admin/agentic/*` |
| **agent-orchestrator-svc** | FastAPI Python | 8087 | 9-stage LangGraph pipeline |
| **mcp_research** | FastAPI Python | 8094 | URL fetch + HTML extract |
| **mcp_tests** | FastAPI Python | 8095 | Real ruff/pytest/mypy |
| **mcp_deploy** | FastAPI Python | 8096 | §42 hard-stop deploy gates |
| **mcp_observe** | FastAPI Python | 8097 | Prom + AM real backings |
| **mcp_hr / itsm / drills** | FastAPI Python | 8091-3 | Prod MCP fleet |
| **Postgres** | Postgres 16 | 5432 | Tasks, runs, audit, RLS-isolated |
| **Qdrant** | Qdrant 1.x | 6333 | 100GB vector store |
| **Prometheus + Alertmanager** | Prom 2.x | 9090, 9093 | Metrics + alerts |
| **Grafana** | Grafana 10 | 3001 | Dashboards |
| **OTel Collector** | OTel | 4317/4318 | Span aggregation |

## Cross-cutting concerns (mapped to brutal-review #s)

| Concern | Container | Status |
|---|---|---|
| **Circuit breakers** | every external dep | ✅ canonical CB everywhere; DbCircuitBreaker (P0c) |
| **Body size limit** | Orch (P1) | ✅ 1 MiB cap |
| **Rate limit** | Orch | ⏸ wired at gateway; per-tenant TODO |
| **Identity boundary (#31)** | Orch | ⏸ JWT validation TODO |
| **Tenant isolation** | Postgres | ✅ RLS on all 12 tenant tables (drilled) |
| **Idempotency** | Orch (#37) | ✅ Schema + helpers (#21 multi-pod store TODO) |
| **Memory bounds** | InMemoryTaskStore (#35) | ✅ LRU bounded (P0a) |
| **Graceful shutdown** | All MCP stubs (#34) | ✅ lifespan handlers (P0b) |
| **§42 hard stop** | Orch + mcp_deploy | ✅ enforced 3 layers deep |
| **§48 audit row** | Orch /explain | ✅ 23-field schema |

## What changes between L2 and L3

L3 zooms into ONE container at a time. The most critical L3 decompositions to author next:

1. **agent-orchestrator-svc L3** — components: LangGraph DAG, agents (9), pool, router, store, explainability, db_circuit_breaker
2. **mcp_observe L3** — components: prom_query, p95_delta, check_alerts_fired, lifespan
3. **Postgres L3** — components: schema migrations, RLS policies, tables (groups by domain)

These are deferred to a follow-up commit per the principle "C4 docs follow architectural changes, not the other way around."
