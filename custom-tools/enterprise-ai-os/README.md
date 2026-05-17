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
| 31 | `ui/` | ⚠ TRUNCATED — only 6 of N React components shown; cut mid-`GovernancePanel.jsx` |
| 32 | (root: README, requirements, startup.sh) | ✓ verbatim · structure/config only |
| 33 | `GAPS.md` (gap closure section) | ✓ verbatim · the source itself is gap analysis, not code |
| 34 | `integrations/` | ✓ verbatim · 6 real-SDK clients |
| 35 | `identity/` | ✓ verbatim · **2 P0 security bugs flagged in-file + GAPS** |
| 36 | `audit/` | ✓ verbatim · in-memory, not durable |
| 37 | `release_management/` | ✓ verbatim · object-only, no real deploy |
| 38 | `slo/` | ✓ verbatim · evaluator only, no Prometheus wiring |
| 39 | `runbooks/` | ✓ verbatim · 5 markdown runbooks |

## P0 security flags (do not run as-is)

1. **`identity/jwt_auth.py`** defaults the JWT signing secret to
   `"change-me"` if `JWT_SECRET_KEY` is unset → anyone can forge tokens.
2. **`identity/auth_route_example.py`** (the `/auth/token` endpoint from
   Tool Set 35 §7) accepts arbitrary `roles` from the client with NO
   password verification → anyone can grant themselves `admin`.

Both are flagged in the source files with `# ⚠️ SECURITY` headers and
documented as P0 in [GAPS.md](GAPS.md). Do not deploy. Do not even
run the `/auth/token` endpoint on a network-reachable interface.

## What's here

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
├── identity/           ← Tool Set 35: auth (⚠ 2 P0 bugs)
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
├── ui/                 ← Tool Set 31 (truncated)
│   ├── package.json
│   ├── TRUNCATED.md
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── DashboardSummary.jsx
│           ├── AgentGraph.jsx
│           ├── TraceViewer.jsx
│           └── GovernancePanel.jsx (truncated mid-file)
│
└── tests/
    ├── test_slo.py
    ├── test_release.py
    └── test_audit.py
```

## How (not) to run

- **Do NOT** start the FastAPI app exposing `/auth/token` on any
  network-reachable interface until you replace the example route with
  a real password / OAuth flow.
- Python files parse cleanly but have no production wiring (no Postgres
  schema, no Kafka topic config, no OTel collector running).
- React UI is incomplete — `GovernancePanel.jsx` is truncated and the
  `CostPanel` / `IncidentPanel` files referenced in `App.jsx` were
  never shown in source.

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
