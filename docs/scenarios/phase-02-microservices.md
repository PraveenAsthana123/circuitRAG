# Phase 2 — Microservices Scenarios

**Status:** Stub. Content lives on `/tools/microservice-scenarios` and `/tools/rag-scenarios` (Ingestion / Retrieval / Inference / MCP / Governance / Eval / FinOps / Observability / Resilience / System Design).

## Scope

| Category | Scenarios |
| --- | --- |
| Patterns | Database per service · API Gateway · Service Mesh (Istio) · Saga · Outbox · CQRS · Circuit Breaker · Idempotency · Event + DLQ · Bulkhead · Strangler Fig · Sidecar |
| RAG-specific | 36 scenarios across 10 layers (see [/tools/rag-scenarios](../../services/frontend/app/tools/rag-scenarios/page.tsx)) |

## Phase-2 exit criteria

Each scenario must:

1. Have at least one implementing file pointer in `classRef` style.
2. Have one end-to-end test that exercises the pattern (real DB / real queue, not mock).
3. Have a failure drill documented in Phase 1 §6 format.

## Concrete next actions

- [ ] Pick 4 scenarios most critical to the demo story (saga, outbox, CB, idempotency).
- [ ] Write an E2E test per scenario hitting real infra from docker-compose.override.yml.
- [ ] Add to `make test-phase-2` target.
