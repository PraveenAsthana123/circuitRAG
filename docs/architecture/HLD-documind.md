# DocuMind High-Level Design (HLD)

This document is the high-level design for DocuMind.

It describes:

- the system purpose
- major actors
- major subsystems
- service boundaries
- data flow
- control flow
- failure handling
- monitoring and governance

This is the system-level view.
For component-level detail, see:

- [docs/architecture/LLD-documind-by-tool-and-component.md](/mnt/deepa/rag/docs/architecture/LLD-documind-by-tool-and-component.md)
- [docs/architecture/C4-context.md](/mnt/deepa/rag/docs/architecture/C4-context.md)
- [docs/architecture/C4-container.md](/mnt/deepa/rag/docs/architecture/C4-container.md)
- [docs/architecture/C4-component.md](/mnt/deepa/rag/docs/architecture/C4-component.md)

## 1. Purpose

DocuMind is a multi-tenant document-intelligence and control-plane platform.

At a high level, it supports:

- document upload and ingestion
- chunking, embedding, indexing, and graph enrichment
- retrieval-augmented question answering
- agent-assisted tool actions through MCP
- degraded-mode draft fallback and replay
- evaluation, governance, FinOps, and observability

This is not only a RAG application.
It is a distributed system with:

- AI inference
- async pipelines
- governance-sensitive workflows
- resilience and audit requirements

## 2. Primary Actors

| Actor | Purpose |
|---|---|
| Tenant user | upload documents and ask questions |
| Tenant admin | manage tenant-specific usage and privileged workflows |
| Platform admin | observe health, drafts, cost, alerts, and control-plane state |
| Reviewer / evaluator | review HITL cases and evaluation results |
| Worker processes | drain async work, replay drafts, and advance pipelines |

## 3. External Dependencies

| Dependency | Role |
|---|---|
| Ollama | model inference and embeddings |
| MinIO / S3-compatible blob store | raw document storage |
| PostgreSQL | authoritative transactional state |
| Qdrant | vector search |
| Neo4j | graph retrieval |
| Redis | cache, coordination, and counters |
| Kafka | async event backbone |
| MCP servers | tool execution endpoints |

## 4. Top-Level Architecture

At a high level, the architecture is:

```text
Frontend
  -> API Gateway
  -> internal services
      -> identity
      -> ingestion
      -> retrieval
      -> inference
      -> evaluation
      -> governance
      -> finops
      -> observability
  -> data and model backends
  -> MCP tool servers
```

## 5. Core Services

| Service | Main responsibility |
|---|---|
| `api-gateway` | external trust boundary, auth, routing, rate limiting, correlation propagation |
| `identity-svc` | identity, users, tenant and JWT-related trust data |
| `ingestion-svc` | parse, chunk, embed, graph, and index documents |
| `retrieval-svc` | hybrid retrieval across vector, graph, and cache |
| `inference-svc` | prompt construction, model invocation, answer generation, agent orchestration |
| `evaluation-svc` | quality scoring, regression gating, replay evaluation |
| `governance-svc` | policy checks, audit, approvals, draft state, governance workflows |
| `finops-svc` | usage and cost accounting |
| `observability-svc` | SLO and capacity-oriented admin surfaces |
| `frontend` | user and operator UI |

## 6. Major Functional Flows

## 6.1 Document ingestion flow

```text
User uploads document
  -> gateway
  -> ingestion-svc
  -> blob store write
  -> parse
  -> chunk
  -> embed
  -> write vector index
  -> write graph index
  -> persist document and chunk metadata
  -> publish or advance async pipeline state
```

Purpose:

- make documents searchable and governable

## 6.2 Ask / RAG flow

```text
User asks question
  -> gateway
  -> inference-svc
  -> retrieval-svc
  -> vector + graph + cache retrieval
  -> prompt construction
  -> model generation
  -> answer + citations
  -> optional logging, eval, usage events
```

Purpose:

- answer with grounded context

## 6.3 Agent plus MCP action flow

```text
User asks question or action-like request
  -> inference-svc AgentService
  -> RAG answer first
  -> intent detection
  -> scope pre-check
  -> MCP client
  -> MCP server
  -> downstream business action
```

Purpose:

- combine answer generation with safe enterprise action execution

## 6.4 Degraded draft fallback flow

```text
Action request
  -> MCP client
  -> breaker open or dependency failure
  -> draft persisted
  -> degraded result returned
  -> audit recorded
```

Purpose:

- preserve user intent when an action cannot complete now

## 6.5 Replay flow

```text
Pending draft
  -> worker or operator
  -> replay action through MCP
  -> mark replayed on success
  -> keep pending or reject on failure path
  -> audit recorded
```

Purpose:

- restore eventual completion safely after outage or degradation

## 7. Data Architecture

| Store | Role |
|---|---|
| PostgreSQL | authoritative state, audit, drafts, service-owned transactional data |
| Qdrant | semantic vector retrieval |
| Neo4j | graph-enriched retrieval |
| Redis | cache, throttling, rate limiting, short-lived coordination |
| Kafka | async event fan-out and replayable streams |
| MinIO | raw uploaded files |

### Data ownership principle

The relational store remains the system of record for critical business state.
Derived indexes and caches are supporting systems, not primary truth.

## 8. Contract Architecture

The system uses multiple contract layers:

- HTTP contracts at the gateway and service edges
- `proto/` as a contract and evolution signal for internal APIs
- JSON event envelopes and schemas for Kafka
- MCP tool schemas for action execution

The most important principle is:

- contracts must be explicit
- contracts must be versionable
- contracts must fail predictably when invalid

## 9. Reliability And Failure Model

This repo is designed around controlled failure behavior.

### Main reliability mechanisms

- circuit breakers
- bounded retries
- degraded mode
- draft fallback
- replay and rejection workflows
- idempotency
- transactional outbox for event publishing
- consumer dedupe

### Main failure goals

- avoid cascading failure
- preserve intent
- make degraded state visible
- make replay safe
- keep audit truthfulness intact

## 10. Security And Governance Model

High-level controls include:

- gateway-based auth verification
- tenant propagation
- scope and role enforcement
- MCP tool scope checks
- policy and approval workflows
- tamper-evident audit logging
- PII and secure-AI design considerations

This means governance is part of the core architecture, not an afterthought.

## 11. Monitoring And Operations Model

The system should be operated through:

- metrics
- traces
- structured logs
- audit records
- drill and scenario validation

High-level operational areas:

- service health
- latency and error rate
- breaker state
- MCP tool outcomes
- draft backlog and replay lag
- evaluation and quality trends
- cost and token usage

## 12. Scalability Model

The system is designed to scale by layer:

- gateway horizontally
- retrieval independently
- inference independently
- ingestion and workers asynchronously
- Kafka consumers by group and partition
- MCP and downstream actions through bounded failure domains

The most expensive layers are usually:

- inference
- embeddings
- retrieval backends under concurrency
- async backlog and replay after outages

## 13. Deployment Model

The repo supports:

- local development
- compose-based data and model dependencies
- Kubernetes-oriented deployment direction
- Istio and observability integration at scale

The honest current position is:

- the architecture is production-shaped
- not every production hardening layer is fully productized yet

## 14. Key Architecture Decisions

Important design choices include:

- polyglot service stack
- strong service decomposition by concern
- RAG plus MCP instead of answer-only AI
- degraded drafts instead of unsafe synchronous retries
- audit as a first-class control plane concept
- event-driven async architecture where needed

## 15. Main Risks

At HLD level, the main risks are:

- architecture drift between docs and implementation
- operational UX lagging behind backend capability
- contract drift across service and event boundaries
- insufficient benchmark and load evidence
- governance surfaces that are conceptually strong but operationally thin

## 16. Bottom Line

DocuMind is best understood as:

- a distributed AI platform
- a control-plane and workflow-aware RAG system
- a resilience- and governance-oriented reference architecture

Its HLD is defined by:

- strong boundaries
- explicit workflows
- safe failure handling
- observable behavior
- governance-aware action execution
