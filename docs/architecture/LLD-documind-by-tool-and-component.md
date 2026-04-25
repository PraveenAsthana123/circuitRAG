# DocuMind Low-Level Design (LLD) By Tool And Component

This document is the low-level design for DocuMind, organized by tool and component.

It focuses on:

- concrete components
- responsibilities
- key inputs and outputs
- important failure behavior
- monitoring expectations

This is the implementation-oriented view.
For the system-level view, see:

- [docs/architecture/HLD-documind.md](/mnt/deepa/rag/docs/architecture/HLD-documind.md)

## 1. API Gateway

### Main code areas

- [services/api-gateway/cmd/main.go](/mnt/deepa/rag/services/api-gateway/cmd/main.go)
- [services/api-gateway/internal/middleware](/mnt/deepa/rag/services/api-gateway/internal/middleware)
- [services/api-gateway/internal/proxy](/mnt/deepa/rag/services/api-gateway/internal/proxy)

### Responsibilities

- terminate external API traffic
- verify JWTs and trust boundaries
- propagate tenant, user, roles, and correlation data
- rate limit and body-limit requests
- route traffic to internal services

### Inputs

- browser or client HTTP requests
- JWTs and headers

### Outputs

- proxied internal requests
- normalized HTTP responses

### Key risks

- auth propagation bugs
- route misconfiguration
- error-envelope drift
- latency amplification under downstream failure

### Monitor

- p50, p95, p99 latency
- 4xx and 5xx rates
- auth failures
- route-level failures

## 2. Identity Service

### Main code areas

- [services/identity-svc](/mnt/deepa/rag/services/identity-svc)

### Responsibilities

- identity and tenant-related state
- JWT and trust-model support
- user and role management

### Key risks

- wrong claims
- tenant mismatch
- stale auth behavior

### Monitor

- login and auth failure rates
- JWT-related errors
- tenant propagation correctness

## 3. Ingestion Service

### Main code areas

- [services/ingestion-svc/app/services/ingestion_service.py](/mnt/deepa/rag/services/ingestion-svc/app/services/ingestion_service.py)
- [services/ingestion-svc/app/saga/document_saga.py](/mnt/deepa/rag/services/ingestion-svc/app/saga/document_saga.py)
- [services/ingestion-svc/app/parsers](/mnt/deepa/rag/services/ingestion-svc/app/parsers)
- [services/ingestion-svc/app/repositories](/mnt/deepa/rag/services/ingestion-svc/app/repositories)

### Responsibilities

- accept documents
- store raw files
- parse content
- chunk content
- generate embeddings
- write vector and graph indexes
- manage saga state and outbox behavior

### Inputs

- uploaded files
- tenant and request context

### Outputs

- document metadata
- chunks
- embeddings
- indexed state
- outbox events

### Key risks

- partial pipeline writes
- parser failures
- embedding failures
- index-write inconsistencies
- outbox not draining

### Monitor

- upload rate
- parse latency
- chunk count
- embedding latency
- index-write failures
- outbox backlog

## 4. Retrieval Service

### Main code areas

- [services/retrieval-svc/app/services/hybrid_retriever.py](/mnt/deepa/rag/services/retrieval-svc/app/services/hybrid_retriever.py)
- [services/retrieval-svc/app/services/vector_searcher.py](/mnt/deepa/rag/services/retrieval-svc/app/services/vector_searcher.py)

### Responsibilities

- embed or normalize query
- search vector store
- search graph store
- merge or rerank results
- return top-k grounded context

### Inputs

- query
- tenant context
- retrieval strategy

### Outputs

- retrieved chunks and metadata

### Key risks

- slow backends
- empty or weak retrieval
- tenant filter errors
- cache regression

### Monitor

- retrieval latency
- backend timeout rate
- cache hit rate
- retrieval quality trend

## 5. Inference Service

### Main code areas

- [services/inference-svc/app/services/rag_inference.py](/mnt/deepa/rag/services/inference-svc/app/services/rag_inference.py)
- [services/inference-svc/app/services/agent.py](/mnt/deepa/rag/services/inference-svc/app/services/agent.py)
- [services/inference-svc/app/agents/multi_hop_agent.py](/mnt/deepa/rag/services/inference-svc/app/agents/multi_hop_agent.py)
- [services/inference-svc/app/services/ollama_client.py](/mnt/deepa/rag/services/inference-svc/app/services/ollama_client.py)

### Responsibilities

- build prompts
- call model backend
- generate grounded answers
- run answer-plus-action agent flow
- run multi-hop retrieval flow

### Inputs

- ask requests
- retrieval results
- auth, tenant, and correlation context

### Outputs

- answer
- citations
- optional action result

### Key risks

- long model latency
- prompt drift
- weak output quality
- scope or tool routing errors

### Monitor

- answer latency
- timeout rate
- token usage
- action-selected count
- denial count
- degraded count

## 6. MCP Client And MCP Servers

### Main code areas

- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)
- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)
- [mcp/server_hr.py](/mnt/deepa/rag/mcp/server_hr.py)
- [mcp/server_itsm.py](/mnt/deepa/rag/mcp/server_itsm.py)
- [mcp/server_drills.py](/mnt/deepa/rag/mcp/server_drills.py)
- [mcp/drafts.py](/mnt/deepa/rag/mcp/drafts.py)

### Responsibilities

- list tools
- validate and call tools
- enforce per-tool scope
- apply circuit-breaker protection
- persist drafts when degraded
- replay or reject drafts
- export per-tool metrics

### Inputs

- tool name
- tool arguments
- tenant, actor, auth, correlation, idempotency context

### Outputs

- tool result
- structured error
- degraded draft result

### Key risks

- wrong namespace routing
- tool schema drift
- replay conflict
- hidden audit failure
- missing per-tool visibility

### Monitor

- per-tool outcomes
- latency
- breaker state
- degraded draft creation
- replay success
- scope denials

## 7. Circuit Breakers

### Main code areas

- [libs/py/documind_core/circuit_breaker.py](/mnt/deepa/rag/libs/py/documind_core/circuit_breaker.py)
- [libs/py/documind_core/breakers.py](/mnt/deepa/rag/libs/py/documind_core/breakers.py)

### Responsibilities

- isolate dependency failures
- fast-reject unhealthy paths
- enable degraded behavior
- protect budget- and loop-sensitive flows

### Inputs

- dependency result signals
- token and step constraints

### Outputs

- allow or reject decisions
- breaker metrics and state

### Key risks

- threshold mismatch
- recovery window mismatch
- retries fighting the breaker
- missing observability

### Monitor

- state transitions
- rejection counts
- failure counts
- half-open probe behavior

## 8. Evaluation Service

### Main code areas

- [services/evaluation-svc/app](/mnt/deepa/rag/services/evaluation-svc/app)

### Responsibilities

- quality scoring
- regression evaluation
- replay against changed prompts or models
- offline and online eval paths

### Inputs

- answers
- contexts
- feedback
- replay requests

### Outputs

- evaluation results
- regression signals

### Key risks

- stale eval dataset
- weak comparison discipline
- score drift without explanation

### Monitor

- eval throughput
- failure rate
- regression result trends

## 9. Governance Service

### Main code areas

- [services/governance-svc](/mnt/deepa/rag/services/governance-svc)
- [libs/py/documind_core/audit.py](/mnt/deepa/rag/libs/py/documind_core/audit.py)

### Responsibilities

- policy checks
- approvals
- audit storage and integrity
- governance workflows

### Inputs

- action and policy events
- audit writes
- approval requests

### Outputs

- policy decisions
- audit records
- approval state

### Key risks

- silent audit failure
- approval drift
- policy visibility gaps

### Monitor

- denial counts
- audit write failures
- approval backlog

## 10. FinOps Service

### Main code areas

- [services/finops-svc](/mnt/deepa/rag/services/finops-svc)

### Responsibilities

- usage tracking
- token and cost aggregation
- budget-aware reporting

### Inputs

- usage and token events

### Outputs

- cost views
- budget signals

### Key risks

- cost tracking drift
- missing usage events
- weak tenant attribution

### Monitor

- token event rate
- aggregation health
- tenant cost growth

## 11. Observability Service

### Main code areas

- [services/observability-svc](/mnt/deepa/rag/services/observability-svc)

### Responsibilities

- admin SLO surfaces
- capacity views
- observability-oriented APIs

### Inputs

- service health and metrics

### Outputs

- admin-facing health and capacity data

### Key risks

- dashboards not matching operator needs
- missing metric sources

### Monitor

- source freshness
- admin API latency

## 12. Frontend

### Main code areas

- [services/frontend/app](/mnt/deepa/rag/services/frontend/app)
- [services/frontend/components](/mnt/deepa/rag/services/frontend/components)
- [services/frontend/lib](/mnt/deepa/rag/services/frontend/lib)

### Responsibilities

- upload and ask UX
- document views
- admin/operator views
- frontend error handling

### Inputs

- user navigation and form input
- gateway APIs

### Outputs

- rendered UI
- user-visible states

### Key risks

- weak failed-request UX
- stale admin placeholders
- browser-only failures

### Monitor

- page load behavior
- browser errors
- failed API rendering

## 13. Kafka And Async Event Backbone

### Main code areas

- [libs/py/documind_core/kafka_client.py](/mnt/deepa/rag/libs/py/documind_core/kafka_client.py)
- [services/ingestion-svc/migrations/002_outbox.sql](/mnt/deepa/rag/services/ingestion-svc/migrations/002_outbox.sql)

### Responsibilities

- async transport
- replayable event streams
- producer and consumer decoupling
- outbox-backed delivery

### Key risks

- outbox drift
- lag
- poison messages
- replay duplication

### Monitor

- producer failures
- consumer lag
- DLQ depth
- oldest message age

## 14. Data Stores

### PostgreSQL

Role:

- source of truth
- audit
- drafts
- service-owned transactional state

Watch:

- query latency
- lock contention
- storage growth

### Qdrant

Role:

- vector retrieval

Watch:

- search latency
- collection health
- payload filter performance

### Neo4j

Role:

- graph retrieval

Watch:

- query latency
- traversal cost
- graph update success

### Redis

Role:

- cache
- counters
- rate-limiting support

Watch:

- hit ratio
- memory pressure
- eviction behavior

### MinIO

Role:

- blob store

Watch:

- write failures
- object availability

## 15. Observability Toolchain

### OpenTelemetry

Role:

- end-to-end traces

### Prometheus

Role:

- metrics storage

### Grafana

Role:

- dashboards

### Langfuse or Phoenix

Role:

- AI run visibility

The LLD expectation is:

- all critical request paths should be measurable
- all critical action paths should be traceable
- degraded and replay paths should be visible

## 16. Bottom Line

At LLD level, this repo is defined by:

- explicit service components
- explicit tool and control-plane components
- explicit data backends
- explicit failure and observability mechanisms

This is the level where:

- responsibilities become code
- workflows become functions
- resilience becomes state machines
- governance becomes stored and observable behavior
