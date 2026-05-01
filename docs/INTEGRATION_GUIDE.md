# Integration Guide

> §19 mandate. Substantive content lives at:
>
> See: [`docs/architecture/per-integration-architecture-and-monitoring-checklist.md`](architecture/per-integration-architecture-and-monitoring-checklist.md) — per-integration design
> See: [`docs/architecture/repo-fit-integration-matrix.md`](architecture/repo-fit-integration-matrix.md) — integration fit matrix
> See: [`docs/architecture/repo-grpc-and-microservice-architecture.md`](architecture/repo-grpc-and-microservice-architecture.md) — service-to-service

## Integration surfaces

| Surface | Pattern | Doc |
|---|---|---|
| Frontend → API gateway | fetch + correlation_id + tenant header | `services/frontend/lib/api.ts` |
| Service ↔ Service | gRPC + Istio mesh + breakers | `repo-grpc-and-microservice-architecture.md` |
| Service ↔ Postgres | asyncpg or pgxpool with prepared statements + RLS | per-service `migrations/*.sql` |
| Service ↔ Redis | aioredis (Python) or go-redis with sliding-window | rate_limiter + cache |
| Service ↔ Kafka | confluent-kafka-go / aiokafka with idempotency keys | event-driven (§41.5) |
| MCP tool calls | MCPClient with breaker per namespace | `services/agent-orchestrator-svc/app/main.py` |

## Connection checklist (CLAUDE.md §14.2)

- [ ] CORS origins from config (no `*`)
- [ ] Auth header injected by API client
- [ ] X-Tenant-ID propagated end-to-end
- [ ] X-Correlation-ID stamped at edge, propagated everywhere
- [ ] Health check (`/health` or `/health/live`+`/health/ready`)
- [ ] Timeout on every external call
- [ ] Circuit breaker per upstream
- [ ] Idempotency key on every POST creating a resource

## Frontend API client pattern

See [`services/frontend/lib/api.ts`](../services/frontend/lib/api.ts):
centralized `fetch` wrapper with timeout, AbortController, error
envelope parsing, X-Tenant-ID + X-Correlation-ID injection.

## Backend → backend pattern

Service-to-service calls go through:
1. **Service mesh** (Istio) for mTLS + L7 routing
2. **Circuit breaker** (`obs_breaker` decorator) per namespace
3. **OTel propagation** via baggage (CLAUDE.md §47.10 baggage propagation)
4. **Tenant context** preserved via `TenantContextMiddleware`
