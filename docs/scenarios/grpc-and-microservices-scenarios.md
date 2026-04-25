# gRPC And Microservices Scenarios

This note lists useful scenarios for gRPC and microservice systems, with monitoring expectations.

It is written in a way that fits this repo’s architecture and likely direction.

## 1. Contract Scenarios

- protobuf schema changes without breaking existing clients
- new optional field added to response
- removed or renamed field causes compatibility break
- service version mismatch between caller and callee
- gateway contract drift from internal service contract

### Monitor

- error rate by method
- serialization or validation failures
- contract-test failures in CI

## 2. Auth And Context Propagation Scenarios

- auth verified at gateway and propagated correctly
- tenant ID preserved across service hops
- correlation ID preserved across service hops
- missing tenant or auth context causes rejection
- wrong tenant propagated to downstream service

### Monitor

- denial rates
- trace continuity
- correlation mismatch incidents
- tenant mismatch or missing-context alerts

## 3. Timeout And Retry Scenarios

- gateway timeout shorter than downstream timeout
- downstream timeout with retry
- retries create load amplification
- retry collides with breaker-open behavior
- deadline exceeded propagates correctly

### Monitor

- timeout rate
- retry rate
- breaker-open rate
- latency inflation across service chain

## 4. Routing Scenarios

- gateway routes request to wrong service
- service discovery points to stale target
- internal route missing after deployment
- one service instance unhealthy while others are healthy
- route-level auth mismatch

### Monitor

- 404 and 5xx rate by route
- gateway routing errors
- health-check failures
- deployment-change correlation with traffic failures

## 5. Load And Saturation Scenarios

- retrieval service saturates before gateway
- inference service saturates before retrieval
- one tenant dominates shared service capacity
- queue builds up behind a slow dependency
- horizontal scaling helps one service but not another

### Monitor

- p95 and p99 latency
- queue depth
- worker lag
- per-service saturation
- tenant-level traffic skew

## 6. Failure Isolation Scenarios

- one service fails while others remain healthy
- governance service slowdowns affect action paths
- identity service failures affect protected endpoints
- retrieval backend degraded but gateway remains healthy
- MCP service degraded but answer path remains available

### Monitor

- dependency-specific error rates
- breaker state by dependency
- degraded-mode counts
- blast-radius evidence in traces

## 7. gRPC-Specific Scenarios

- unary RPC succeeds normally
- unary RPC exceeds deadline
- streaming RPC interrupted mid-stream
- client uses older proto version
- server adds field and old client ignores it safely

### Monitor

- method latency
- deadline exceeded status count
- stream interruption count
- compatibility failures

## 8. Microservice Workflow Scenarios

- upload triggers ingestion pipeline
- ask request triggers retrieval and inference
- action request triggers MCP flow
- degraded action creates draft
- replay worker resolves draft later

### Monitor

- end-to-end trace coverage
- workflow success rate
- degraded rate
- replay lag
- audit visibility

## 9. Operational Monitoring Matrix

| Scenario family | Metrics | Traces | Logs | Dashboards |
|---|---|---|---|---|
| Contracts | validation and error counts | optional | schema mismatch logs | CI and contract board |
| Auth and context | denial counts | required | auth and tenant logs | access dashboard |
| Timeout and retry | timeout and retry counts | required | dependency timeout logs | latency and retry board |
| Routing | route error rates | required | gateway route logs | gateway board |
| Load and saturation | p95, p99, queue depth, saturation | required | service pressure logs | capacity dashboard |
| Failure isolation | degraded counts, breaker state | required | failure-domain logs | resilience dashboard |
| Workflow | replay, draft, audit metrics | required | workflow logs | control-plane dashboard |

## 10. Highest-Value Scenarios For This Repo

1. gateway -> retrieval -> inference trace continuity
2. auth and tenant propagation across service hops
3. timeout and retry behavior under downstream slowdown
4. MCP degraded draft creation under outage
5. replay recovery after outage
6. service-level saturation and backlog growth
7. route and contract drift after deployment

## 11. Bottom Line

The most important gRPC and microservice scenarios are not about transport alone.

They are about:

- contract stability
- context propagation
- timeout and retry discipline
- failure isolation
- observability
- workflow correctness

That is what should be monitored and tested in this repo.
