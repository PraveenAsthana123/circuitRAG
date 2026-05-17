# enterprise-ai-os — alternative-approach exploration (Python + React)

> **Status: study / interview material, NOT production-grade.**
> A separate exploration from `../openclaw-components/`. Same kind of
> source — interview-style "Tool Sets" with a "Production value: Yes"
> framing that overstates what's actually implemented. Honest gap
> review per CLAUDE.md §47 / §52 / §43 lives in [GAPS.md](GAPS.md).

## Source-fidelity notes

| Tool Set | Folder | Status |
|----------|--------|--------|
| 1–10 | — | ✗ NOT in source paste |
| 11 | `explainability_ai/` | ✓ verbatim · backfilled from gap · **does NOT meet CLAUDE.md §48 explainability** — see GAPS.md |
| 12–30 | — | ✗ NOT in source paste |
| 31 | `ui/` | ⚠ reconstructed from truncated source; builds with local stubs and shared API client |
| 32 | (root: README, requirements, startup.sh) | ✓ verbatim · structure/config only |
| 33 | `GAPS.md` (gap closure section) | ✓ verbatim · the source itself is gap analysis, not code |
| 34 | `integrations/` | ✓ verbatim · 6 real-SDK clients |
| 35 | `identity/` | ✓ P0 JWT-secret and token-role bugs fixed; remaining gaps in GAPS.md |
| 36 | `audit/` | ✓ verbatim · in-memory, not durable |
| 37 | `release_management/` | ✓ verbatim · object-only, no real deploy |
| 38 | `slo/` | ✓ verbatim · evaluator only, no Prometheus wiring |
| 39 | `runbooks/` | ✓ verbatim · 5 markdown runbooks |

## Security status

The two earlier Tool Set 35 P0 issues are fixed in code and covered by negative drills:

1. `identity/jwt_auth.py` refuses unset, weak, or default `JWT_SECRET_KEY` values.
2. `identity/auth_route_example.py` authenticates credentials and derives `tenant_id` and `roles` server-side instead of trusting client-claimed roles.

This folder is still study material, not production-grade; remaining deployment blockers are tracked in [GAPS.md](GAPS.md).

## What is included

```
enterprise-ai-os/
├── README.md           ← you are here
├── GAPS.md             ← honest review per tool set
├── requirements.txt    ← Tool Set 32 + accumulated additions
├── .env.example        ← Tool Set 34 + Tool Set 35 envs
├── startup.sh          ← Tool Set 32
│
├── explainability_ai/  ← Tool Set 11: reasoning trace + attribution
│   ├── reasoning_trace.py
│   ├── source_attribution.py
│   ├── confidence_report.py
│   ├── decision_path.py
│   └── explainability_engine.py
│
├── integrations/       ← Tool Set 34: real-SDK clients
│   ├── openai_client.py
│   ├── qdrant_client.py
│   ├── postgres_client.py
│   ├── redis_client.py
│   ├── kafka_client.py
│   └── otel_sdk.py
│
├── identity/           ← Tool Set 35: auth (P0 drills fixed; still not production auth)
│   ├── jwt_auth.py
│   ├── user_store.py
│   ├── tenant_store.py
│   ├── role_assignment.py
│   ├── auth_dependency.py
│   ├── auth_route_example.py
│   └── protected_route_example.py
│
├── audit/              ← Tool Set 36: append-only hash chain
│   ├── hash_chain.py
│   ├── immutable_audit_store.py
│   └── audit_exporter.py
│
├── release_management/ ← Tool Set 37
│   ├── agent_release.py
│   ├── prompt_release.py
│   ├── canary_manager.py
│   ├── rollback_manager.py
│   └── release_engine.py
│
├── slo/                ← Tool Set 38
│   ├── slo_policy.py
│   ├── error_budget.py
│   ├── slo_report.py
│   └── alert_rules.py
│
├── runbooks/           ← Tool Set 39: 5 markdown runbooks
│   ├── llm_outage.md
│   ├── vector_db_down.md
│   ├── high_latency.md
│   ├── hallucination_incident.md
│   └── governance_failure.md
│
├── ui/                 ← Tool Set 31 (reconstructed UI)
│   ├── package.json
│   ├── TRUNCATED.md
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── DashboardSummary.jsx
│           ├── AgentGraph.jsx
│           ├── TraceViewer.jsx
│           ├── GovernancePanel.jsx
│           ├── CostPanel.jsx
│           └── IncidentPanel.jsx
│
└── tests/
    ├── test_slo.py
    ├── test_release.py
    └── test_audit.py
```

## How (not) to run

- Do not expose this example auth flow as production SSO; it is credential-backed study code and still lacks MFA, rate limits, durable audit, and revocation.
- Python files parse cleanly but have no production wiring (no Postgres
  schema, no Kafka topic config, no OTel collector running).
- React UI source was reconstructed where the paste was incomplete; it now builds, uses `VITE_API_BASE_URL`, supports bearer tokens from local storage, and aborts in-flight requests on unmount.

## Cross-reference with circuitRAG real services

| Tool Set | What it explores | circuitRAG counterpart |
|----------|------------------|-----------------------|
| 34 OpenAI client | LLM SDK wrapping | `services/inference-svc/` |
| 34 Qdrant client | Vector search | `services/retrieval-svc/` (already pgvector) |
| 34 Postgres | DB connection | `libs/py/documind_core/` (uses asyncpg + RLS) |
| 34 Kafka | Event backbone | `services/ingestion-svc/` (existing Kafka) |
| 34 OTel | Tracing | Real OTel collector already in `ops-compose/` |
| 35 JWT | Auth | OIDC/JWKS already done; do NOT copy this insecure version |
| 36 Hash-chain audit | Tamper evidence | `mcp/server_audit.py` + Postgres append-only table |
| 37 Release management | Deploy + rollback | Argo Rollouts + `docs/architecture/rollout/` |
| 38 SLO | SLO tracking | Prometheus + Grafana dashboards (already in `ops-compose/`) |

Most of this exists in `services/` already at higher quality. This
folder is a study artifact, not an upgrade path.
