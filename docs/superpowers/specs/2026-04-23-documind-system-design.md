# DocuMind — AI-Powered Enterprise Document Intelligence Platform

## Complete System Design Specification

**Date:** 2026-04-23
**Author:** Praveen + Claude
**Status:** Draft
**Stack:** Python (AI/ML) + Go (Gateway/Governance/Infra) + TypeScript (Frontend) + Kind + Istio
**LLM:** Ollama (Llama 3, Mistral, Phi-3) — fully local
**Timeline:** 8-12 weeks, deep learning mode

---

## Table of Contents

1. [Project Identity](#1-project-identity)
2. [Architecture Overview](#2-architecture-overview)
3. [Design Area Mapping (All 67 + Extras)](#3-design-area-mapping)
4. [Microservice Specifications](#4-microservice-specifications)
5. [Data Architecture](#5-data-architecture)
6. [Infrastructure & Deployment](#6-infrastructure--deployment)
7. [Build Sequence (Weekly Plan)](#7-build-sequence)
8. [Interview Talking Points per Design Area](#8-interview-talking-points)

---

## 1. Project Identity

**Name:** DocuMind
**One-liner:** Multi-tenant SaaS platform where organizations upload documents, the system ingests/chunks/embeds/indexes them, and users ask natural language questions answered via RAG with citations — governed by evaluation pipelines, observability, and tenant-aware billing.

### Core User Stories

1. **Tenant Admin** uploads documents (PDF, DOCX, TXT, HTML) → system ingests, chunks, embeds, stores in vector + graph DB
2. **Tenant User** asks a question → system retrieves relevant chunks (vector + graph hybrid), reranks, generates answer with citations
3. **Platform Admin** views cross-tenant metrics, cost, model health, drift alerts on observability dashboard
4. **Evaluator** runs offline/online evaluation pipelines to measure retrieval quality (precision/recall/MRR) and answer accuracy (faithfulness, relevance)
5. **Governance Officer** reviews flagged answers, applies human-in-the-loop overrides, manages policies
6. **System** auto-scales, circuit-breaks on Ollama failures, rate-limits per tenant, caches repeated queries, tracks cost per token

---

## 2. Architecture Overview

### 2.1 High-Level Architecture

```
                           ┌─────────────────────────────────────────────────┐
                           │              Kind Kubernetes Cluster             │
                           │              Istio Service Mesh                  │
                           │                                                  │
   Users ──► ┌─────────┐  │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
             │ Next.js  │──┼─►│ API GW   │─►│ Identity  │  │  Ingestion   │  │
             │ Frontend │  │  │ (Go)     │  │ (Go)      │  │  (Python)    │  │
             └─────────┘  │  └────┬─────┘  └───────────┘  └──────┬───────┘  │
                           │       │                               │          │
                           │       ▼                               ▼          │
                           │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
                           │  │Retrieval │  │ Inference │  │  Evaluation  │  │
                           │  │(Python)  │  │ (Python)  │  │  (Python)    │  │
                           │  └──────────┘  └───────────┘  └──────────────┘  │
                           │                                                  │
                           │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
                           │  │Governance│  │   FinOps  │  │Observability │  │
                           │  │(Go)      │  │   (Go)    │  │   (Go)       │  │
                           │  └──────────┘  └───────────┘  └──────────────┘  │
                           │                                                  │
                           │  ┌─────────────────────────────────────────────┐ │
                           │  │              Data Layer                      │ │
                           │  │  PostgreSQL  Qdrant  Neo4j  Redis  Kafka    │ │
                           │  └─────────────────────────────────────────────┘ │
                           │                                                  │
                           │  ┌─────────────────────────────────────────────┐ │
                           │  │              Ollama (GPU Pod)                │ │
                           │  │  Llama 3 │ Mistral │ Phi-3 │ Embeddings    │ │
                           │  └─────────────────────────────────────────────┘ │
                           └─────────────────────────────────────────────────┘
```

### 2.2 Communication Patterns

| Pattern | Where Used | Protocol |
|---------|-----------|----------|
| Sync request-response | Frontend → API GW → Services | gRPC + REST (gateway translates) |
| Async event-driven | Ingestion → Embedding → Indexing pipeline | Kafka topics |
| Pub/Sub notifications | Alerts, job completion, policy violations | Kafka + Redis Pub/Sub |
| Sidecar proxy | All inter-service traffic | Istio Envoy |
| Circuit breaker | Ollama calls, external services | Istio DestinationRule + application-level (Go/Python) |

### 2.3 Service Registry

| Service | Language | Port | gRPC Port | Responsibilities |
|---------|----------|------|-----------|-----------------|
| `api-gateway` | Go | 8080 | 9090 | Routing, rate limiting, auth validation, request transformation |
| `identity-svc` | Go | 8081 | 9091 | JWT, RBAC, tenant management, API key management |
| `ingestion-svc` | Python | 8082 | 9092 | Document parsing, chunking, embedding, indexing orchestration |
| `retrieval-svc` | Python | 8083 | 9093 | Vector search, graph traversal, hybrid retrieval, reranking |
| `inference-svc` | Python | 8084 | 9094 | Prompt construction, Ollama orchestration, response generation |
| `evaluation-svc` | Python | 8085 | 9095 | Offline/online eval, regression gates, metrics computation |
| `governance-svc` | Go | 8086 | 9096 | Policy engine, HITL queue, audit logging, compliance |
| `finops-svc` | Go | 8087 | 9097 | Token counting, cost attribution, billing, budget alerts |
| `observability-svc` | Go | 8088 | 9098 | Metrics aggregation, alerting rules, SLO tracking, dashboards |
| `frontend` | TypeScript | 3000 | — | Next.js UI for all user roles |

---

## 3. Design Area Mapping (All 67 + Extras)

### Legend
- **Where:** Which service/component implements this
- **How:** Technical implementation approach
- **Interview:** Key talking point

---

### AREA 1: System Boundary

**Where:** API Gateway + Istio Ingress
**How:**
- Istio `Gateway` + `VirtualService` define the system's external boundary
- API Gateway (Go) is the single entry point — no service is directly exposed
- All external traffic: `User → Istio Ingress → API Gateway → Internal Services`
- Internal services communicate only via mesh (mTLS enforced by Istio)
- System boundary documented as a C4 Context Diagram

```yaml
# Istio Gateway definition
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: documind-gateway
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 443
      name: https
      protocol: HTTPS
    hosts:
    - "documind.local"
```

**Sub-areas covered:**
- **System Architect / System Overview:** The architecture diagram above IS the system overview
- **Pipeline:** Ingestion pipeline (upload → parse → chunk → embed → index) runs as Kafka-orchestrated workflow
- **Microservice Screening:** Each service passed the "does it have an independent lifecycle?" test — Ingestion can scale independently of Retrieval, Inference can restart without affecting Governance
- **Observability and Monitoring:** Every service emits OpenTelemetry traces + Prometheus metrics, collected by Observability Service
- **Execution:** Kubernetes manages execution — pod scheduling, health checks, restarts, resource limits

**Interview:** "Our system boundary is defined at two levels: Istio Ingress Gateway for L4/L7 traffic control and mTLS enforcement, and our Go API Gateway for application-level concerns like authentication, rate limiting, and request transformation. No internal service is directly reachable from outside the mesh."

---

### AREA 2: Responsibility Boundary

**Where:** Each microservice + API contracts
**How:**
- Each service owns ONE bounded context (DDD terminology)
- Service responsibilities documented in a RACI matrix
- No service directly accesses another service's database (database-per-service pattern)

| Service | Owns | Does NOT Own |
|---------|------|-------------|
| Identity | Users, tenants, roles, API keys | Documents, embeddings |
| Ingestion | Document parsing, chunking, embedding orchestration | Retrieval, answer generation |
| Retrieval | Search execution, reranking | Document storage, LLM calls |
| Inference | Prompt construction, LLM orchestration | Document parsing, evaluation |
| Evaluation | Eval datasets, metrics, regression gates | Answer generation, billing |
| Governance | Policies, HITL queue, audit log | User auth, document storage |
| FinOps | Token counts, cost, budgets | Everything else |
| Observability | Metrics, alerts, SLOs | Business logic |

**Sub-areas covered:**
- **System Context Diagram:** C4 Level 1 shows DocuMind, its users (tenant admin, user, platform admin, evaluator), and external systems (Ollama, file storage)
- **Identify All External Access:** External boundaries: Ollama API, file uploads (S3-compatible MinIO), email notifications (SMTP), webhook callbacks
- **Boundary Document:** Each service has a `BOUNDARIES.md` describing what it owns, its API surface, and what it delegates
- **Threat Model:** STRIDE analysis per boundary — spoofing (JWT validation), tampering (mTLS + checksums), repudiation (audit log), information disclosure (tenant isolation), DoS (rate limiting), elevation (RBAC)

**Interview:** "We apply the database-per-service pattern strictly. Ingestion Service owns its PostgreSQL schema for document metadata and writes to Qdrant/Neo4j. Retrieval Service reads from Qdrant/Neo4j but never writes — that separation makes our read/write paths clean and testable."

---

### AREA 3: Trust Boundary

**Where:** API Gateway + Identity Service + Istio mTLS
**How:**
- **External → Internal:** Zero trust. Every request authenticated at API Gateway (JWT validation), authorized at service level (RBAC check)
- **Service → Service:** Istio mTLS (automatic mutual TLS). Services trust the mesh identity, not raw network access
- **Service → Data Store:** Each service has its own credentials. Ingestion cannot read Governance's audit tables
- **Service → Ollama:** Treated as an untrusted external dependency. Circuit breaker + timeout + output validation (no prompt injection in response)
- **Tenant → Tenant:** Complete data isolation. Tenant ID on every query. Row-level security in PostgreSQL

```
Trust Zones:
┌─────────────────────────────────────────────┐
│ Zone 0 (Untrusted): Internet, Users         │
├─────────────────────────────────────────────┤
│ Zone 1 (DMZ): Istio Ingress, API Gateway    │
├─────────────────────────────────────────────┤
│ Zone 2 (Trusted): Internal services (mTLS)  │
├─────────────────────────────────────────────┤
│ Zone 3 (Restricted): Data stores, Ollama    │
└─────────────────────────────────────────────┘
```

**Interview:** "We define four trust zones. User traffic enters Zone 0, gets authenticated at Zone 1 (API Gateway), then flows through Zone 2 services via Istio mTLS. Data stores in Zone 3 are only accessible from specific services with per-service credentials. Ollama is also Zone 3 — we treat it as untrusted and validate every response."

---

### AREA 4: Failure Boundary

**Where:** Istio DestinationRules + application-level circuit breakers + Kubernetes resource limits
**How:**
- **Blast radius containment:** If Ollama crashes, only Inference Service is affected. Retrieval still returns cached/partial results. Ingestion queues work and retries later
- **Bulkhead pattern:** Each service runs in its own pod with CPU/memory limits. One service's OOM cannot kill another
- **Circuit breaker (Istio):**
  ```yaml
  apiVersion: networking.istio.io/v1beta1
  kind: DestinationRule
  metadata:
    name: inference-circuit-breaker
  spec:
    host: inference-svc
    trafficPolicy:
      connectionPool:
        tcp:
          maxConnections: 100
        http:
          h2UpgradePolicy: DEFAULT
          http1MaxPendingRequests: 100
          http2MaxRequests: 1000
          maxRequestsPerConnection: 10
      outlierDetection:
        consecutive5xxErrors: 5
        interval: 30s
        baseEjectionTime: 60s
        maxEjectionPercent: 50
  ```
- **Circuit breaker (application-level in Python):**
  ```python
  class CircuitBreaker:
      CLOSED = "closed"
      OPEN = "open"
      HALF_OPEN = "half_open"

      def __init__(self, failure_threshold=5, recovery_timeout=60):
          self.state = self.CLOSED
          self.failure_count = 0
          self.failure_threshold = failure_threshold
          self.recovery_timeout = recovery_timeout
          self.last_failure_time = None

      def call(self, func, *args, **kwargs):
          if self.state == self.OPEN:
              if time.time() - self.last_failure_time > self.recovery_timeout:
                  self.state = self.HALF_OPEN
              else:
                  raise CircuitOpenError("Circuit is open")
          try:
              result = func(*args, **kwargs)
              if self.state == self.HALF_OPEN:
                  self.state = self.CLOSED
                  self.failure_count = 0
              return result
          except Exception as e:
              self.failure_count += 1
              self.last_failure_time = time.time()
              if self.failure_count >= self.failure_threshold:
                  self.state = self.OPEN
              raise
  ```

**Interview:** "We implement circuit breaking at two levels. Istio's outlier detection handles infrastructure-level failures — if a pod returns 5 consecutive 5xx errors, it's ejected from the load balancer pool for 60 seconds. At the application level, our Python services wrap Ollama calls in a circuit breaker that tracks failure counts and opens the circuit to fail fast, preventing cascade failures."

---

### AREA 5: Tenant Boundary

**Where:** Identity Service + PostgreSQL RLS + every service
**How:**
- **Tenant model:** Each tenant gets a `tenant_id` (UUID). Every database row, every Kafka message, every cache key, every vector in Qdrant is tagged with `tenant_id`
- **PostgreSQL Row-Level Security:**
  ```sql
  CREATE POLICY tenant_isolation ON documents
      USING (tenant_id = current_setting('app.current_tenant')::uuid);
  ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
  ```
- **Qdrant:** Tenant ID stored as payload filter — every search includes `must: [{key: "tenant_id", match: {value: "<tenant_id>"}}]`
- **Neo4j:** Tenant ID as property on every node. Cypher queries always filter: `WHERE n.tenant_id = $tenant_id`
- **Kafka:** Tenant ID in message headers. Consumer groups per tenant for isolation (or shared with tenant-aware routing)
- **Redis cache keys:** `tenant:{tenant_id}:query:{hash}` — no cross-tenant cache hits
- **Resource quotas:** Per-tenant limits on documents, storage, queries/day, tokens/day

**Interview:** "Tenant isolation is enforced at every layer. PostgreSQL uses row-level security policies that filter by tenant_id set in the session context. Qdrant uses payload filters. Neo4j uses property-based filtering. Even our Redis cache keys are namespaced by tenant. A bug in one service cannot leak data across tenants because the data layer itself enforces isolation."

---

### AREA 6: Control Plane

**Where:** Governance Service + API Gateway + Identity Service
**How:**
The control plane manages HOW the system behaves, not WHAT data flows through it.

| Control Plane Component | Responsibility |
|------------------------|----------------|
| Governance Service | Policy rules, feature flags, model selection policies, HITL routing rules |
| Identity Service | Tenant provisioning, RBAC role definitions, API key lifecycle |
| API Gateway | Rate limit configurations, routing rules, circuit breaker thresholds |
| Kubernetes | Pod scaling policies, resource quotas, network policies |
| Istio | Traffic routing (canary, A/B), mTLS policies, retry policies |

- **Model Control Portal (MCP):** A dedicated admin UI section where platform admins can:
  - View deployed models (Ollama model list)
  - Switch active model per tenant (e.g., Tenant A uses Llama 3, Tenant B uses Mistral)
  - Set model-level rate limits and token budgets
  - View model health metrics (latency p50/p95/p99, error rate, throughput)
  - Trigger model warm-up / preloading
  - Compare model outputs side-by-side (evaluation)

**Interview:** "Our control plane is separated from the data plane. The Governance Service acts as the policy brain — it stores rules like 'Tenant X can use max 10,000 tokens/day' or 'flag any answer with confidence < 0.6 for human review.' These policies are read by data-plane services at runtime via a cached config fetch, not hardcoded."

---

### AREA 7: Data Plane

**Where:** Ingestion + Retrieval + Inference services
**How:**
The data plane handles actual document and query processing:

```
DATA PLANE FLOW:

Upload Path:
  Document → Ingestion → Parser → Chunker → Embedder → [Qdrant + Neo4j + PostgreSQL]
                                                              ▲
                                                         Kafka events

Query Path:
  Question → Retrieval → [Qdrant vector search + Neo4j graph traversal]
           → Reranker → Inference → [Ollama LLM] → Answer + Citations
                                                         │
                                                    Kafka events
                                                         ▼
                                              FinOps (token counting)
                                              Evaluation (quality tracking)
```

- Data plane services are stateless (all state in data stores)
- Horizontally scalable — add more Retrieval pods for more query throughput
- Data plane reads policies from control plane at startup + periodically refreshes

**Interview:** "The data plane is where documents and queries flow. It's completely stateless — all state lives in PostgreSQL, Qdrant, Neo4j, and Redis. This means we can scale any data-plane service horizontally by adding pods. The control plane tells data-plane services HOW to behave (which model, what limits), but doesn't participate in the hot path."

---

### AREA 8: Management Plane

**Where:** Observability Service + FinOps Service + Kubernetes API + admin UI
**How:**
The management plane handles operational concerns:

| Function | Component |
|----------|-----------|
| Monitoring | Prometheus + Grafana (via Observability Service) |
| Logging | Structured JSON logs → Loki (or stdout for Kind) |
| Tracing | OpenTelemetry → Jaeger |
| Alerting | Prometheus AlertManager rules defined in Observability Service |
| Cost tracking | FinOps Service aggregates token usage per tenant |
| Capacity planning | Kubernetes metrics + custom capacity model in Observability |
| Incident management | Alert → PagerDuty/Slack webhook (simulated locally) |

**Interview:** "Our management plane is the operational lens. It doesn't touch user data but gives platform admins visibility into system health, cost, and capacity. The Observability Service aggregates metrics from all services, the FinOps Service tracks token spend, and Kubernetes gives us resource utilization. We expose this through an admin dashboard."

---

### AREA 9: State Model

**Where:** Each service defines its own state machine
**How:**

**Document State Machine:**
```
UPLOADED → PARSING → PARSED → CHUNKING → CHUNKED → EMBEDDING → EMBEDDED → INDEXING → INDEXED → ACTIVE
    │          │         │          │          │           │          │           │          │
    ▼          ▼         ▼          ▼          ▼           ▼          ▼           ▼          ▼
  FAILED    FAILED    FAILED    FAILED     FAILED      FAILED    FAILED      FAILED    ARCHIVED
```

**Query State Machine:**
```
RECEIVED → RETRIEVING → RETRIEVED → GENERATING → GENERATED → DELIVERED
    │           │            │            │            │
    ▼           ▼            ▼            ▼            ▼
  FAILED    FAILED      FAILED      FAILED      FLAGGED → HUMAN_REVIEW → APPROVED/REJECTED
```

**Job State Machine (background tasks):**
```
QUEUED → RUNNING → COMPLETED
   │        │
   ▼        ▼
 CANCELLED FAILED → RETRYING → RUNNING
```

- State transitions logged to audit table with timestamp, actor, reason
- Invalid transitions rejected (e.g., cannot go from FAILED to ACTIVE without re-processing)
- State stored in PostgreSQL with optimistic locking (version column)

**Interview:** "Every entity has a well-defined state machine. Documents go through UPLOADED → PARSING → CHUNKED → EMBEDDED → INDEXED → ACTIVE. Each transition is logged in the audit table. Invalid transitions are rejected at the repository layer. We use optimistic locking with a version column to prevent concurrent state corruption."

---

### AREA 10: Session State

**Where:** Redis + API Gateway
**How:**
- User sessions stored in Redis with TTL (30 minutes default, configurable per tenant)
- Session contains: `user_id`, `tenant_id`, `roles`, `preferences`, `last_activity`
- Conversation history (chat context) stored in Redis sorted sets keyed by `session:{id}:history`
- Session state is NOT in any service's memory — fully externalized for horizontal scaling
- Sticky sessions NOT used — any pod can serve any request because session is in Redis

```
Redis Keys:
  session:{session_id}              → {user_id, tenant_id, roles, expires_at}
  session:{session_id}:history      → sorted set of {timestamp, message} pairs
  session:{session_id}:context      → last N retrieved chunks (for follow-up questions)
```

**Interview:** "Sessions are fully externalized to Redis. No service holds session state in memory, which means any pod can serve any request. This is critical for horizontal scaling and rolling deployments — we can restart any pod without losing user sessions."

---

### AREA 11: Agent State

**Where:** Inference Service + Redis + PostgreSQL
**How:**
DocuMind supports multi-step "agent" workflows where the system autonomously:
1. Breaks a complex question into sub-questions
2. Retrieves information for each sub-question
3. Synthesizes a final answer

**Agent state machine:**
```
PLANNING → STEP_N_RETRIEVING → STEP_N_REASONING → ... → SYNTHESIZING → COMPLETE
                                                              │
                                                           FAILED / TIMEOUT
```

- Agent execution state stored in Redis (fast reads/writes during execution)
- Completed agent traces persisted to PostgreSQL (for evaluation and audit)
- Max steps limit (configurable, default 5) prevents infinite loops
- Timeout per step (30s) and per agent run (120s)
- Each step logs: `{step_id, action, input, output, tokens_used, latency_ms}`

**Interview:** "For multi-step reasoning, the agent state is stored in Redis during execution for performance, then persisted to PostgreSQL on completion. We enforce guardrails — max 5 steps, 30-second timeout per step, 120-second total timeout — to prevent runaway agents. Every step is logged for observability and evaluation."

---

### AREA 12: Consistency Model

**Where:** Cross-cutting across all services
**How:**

| Data Store | Consistency Model | Rationale |
|-----------|-------------------|-----------|
| PostgreSQL | Strong (SERIALIZABLE for critical, READ COMMITTED default) | User data, tenant config, audit logs need strong consistency |
| Qdrant | Eventual | Vector index updates can lag slightly — search quality degrades gracefully |
| Neo4j | Causal (read-your-own-writes) | Graph traversal needs to see recently added entities |
| Redis | Eventual (with TTL-based invalidation) | Cache — staleness is acceptable within TTL |
| Kafka | At-least-once delivery + idempotent consumers | Events may be replayed — consumers must handle duplicates |

- **Cross-service consistency:** We use the Saga pattern (not distributed transactions). If embedding fails after chunking succeeded, the saga compensates by marking the document as FAILED and cleaning up partial chunks
- **Read-your-own-writes guarantee:** After a user uploads a document, subsequent API calls for that user include a consistency token that forces fresh reads

**Interview:** "We don't use distributed transactions. Instead, we use the Saga pattern with compensation. If the embedding step fails after chunking succeeded, the saga coordinator marks the document as FAILED and publishes a cleanup event. Each data store uses the consistency model appropriate for its use case — strong for PostgreSQL, eventual for vector search, causal for graph queries."

---

### AREA 13: Read Path vs Write Path

**Where:** Retrieval Service (read) + Ingestion Service (write) — CQRS within the document domain
**How:**

**Write Path (Ingestion):**
```
Document Upload → API GW → Ingestion Service
  → Parse document (extract text, tables, images)
  → Chunk text (recursive splitter, 512 tokens, 50 overlap)
  → Generate embeddings (Ollama embed model)
  → Write to Qdrant (vectors) + Neo4j (entities/relationships) + PostgreSQL (metadata)
  → Publish event: document.indexed
```
- Write path is async (Kafka-driven pipeline)
- Optimized for throughput, not latency
- Writes go to all three stores (fan-out)

**Read Path (Retrieval):**
```
User Query → API GW → Retrieval Service
  → Check Redis cache (query hash)
  → If miss: parallel search [Qdrant (vector) + Neo4j (graph) + PostgreSQL (metadata)]
  → Merge + Rerank results (cross-encoder or reciprocal rank fusion)
  → Cache result in Redis (TTL: 5 minutes)
  → Return top-K chunks to Inference Service
```
- Read path is sync (user waiting)
- Optimized for latency (cache, parallel search, pre-computed indexes)
- Reads from all three stores (fan-in)

**Separation benefits:**
- Write path can be scaled independently (more Kafka consumers for bulk uploads)
- Read path can be scaled independently (more Retrieval pods for query spikes)
- Different optimization strategies (write: throughput, read: latency)
- Can rebuild read models from write events (event sourcing lite)

**Interview:** "We apply CQRS at the domain level. The write path runs through Ingestion as an async Kafka pipeline optimized for throughput — it fan-outs to Qdrant, Neo4j, and PostgreSQL. The read path runs through Retrieval as sync requests optimized for latency — it fan-ins from all three stores in parallel, reranks, and caches. The two paths scale independently."

---

### AREA 14: Admin Path Isolation

**Where:** API Gateway + separate admin endpoints + Governance Service
**How:**
- Admin endpoints are on a separate URL prefix: `/api/v1/admin/*`
- Admin traffic gets separate rate limits (stricter on writes, relaxed on reads)
- Admin actions require elevated roles (`platform_admin`, `tenant_admin`)
- Admin endpoints have separate Istio `VirtualService` routing (can be weighted differently)
- Admin audit trail: every admin action logged with actor, action, target, timestamp, IP
- Admin operations never share connection pools with user operations (separate DB connection pools)

```
User traffic:  /api/v1/documents/*  → Ingestion/Retrieval (standard pool)
Admin traffic: /api/v1/admin/*      → Governance/Identity (admin pool)
```

**Interview:** "Admin paths are fully isolated from user paths. They use separate URL prefixes, separate rate limits, separate DB connection pools, and separate Istio routing rules. This prevents an admin bulk operation from starving user queries. Every admin action is audit-logged."

---

### AREA 15: Evaluation Path Isolation

**Where:** Evaluation Service (dedicated pods) + separate data pipelines
**How:**
- Evaluation runs on dedicated pods that do NOT serve production traffic
- Eval datasets stored in a separate PostgreSQL schema (`eval.*`)
- Eval queries go through the same Retrieval + Inference pipeline but are tagged as `eval=true`
- Tagged requests: FinOps does NOT bill them, Observability tracks them separately
- Eval jobs run during off-peak hours (cron-scheduled) or on-demand
- Eval results written to `eval.results` table, never mixed with production data

```
Eval Pipeline:
  Eval Dataset (questions + ground truth)
    → Retrieval Service (tagged eval=true)
    → Inference Service (tagged eval=true)
    → Compare output vs ground truth
    → Compute metrics: faithfulness, relevance, precision@k, recall@k, MRR, NDCG
    → Store in eval.results
    → If regression detected → block deployment (regression gate)
```

**Interview:** "Evaluation runs on isolated pods with separate data. We tag eval requests so they don't affect billing or production metrics. The evaluation pipeline computes retrieval metrics (precision@k, MRR) and generation metrics (faithfulness, relevance) against ground truth datasets. A regression gate can block deployments if quality drops."

---

### AREA 16: Sync vs Async

**Where:** Cross-cutting design decision for every operation
**How:**

| Operation | Pattern | Reason |
|-----------|---------|--------|
| User login | Sync | User waiting, fast (< 100ms) |
| Document upload (initiate) | Sync | Return upload ID immediately |
| Document processing pipeline | Async (Kafka) | Long-running, multi-step |
| User query (chat) | Sync | User waiting for answer |
| Embedding generation | Async (Kafka consumer) | CPU/GPU intensive, batched |
| Evaluation run | Async (background job) | Minutes to hours |
| Report generation | Async (background job) | Aggregation over large datasets |
| Audit log write | Async (fire-and-forget via Kafka) | Should not block request path |
| Cache invalidation | Async (Kafka event-driven) | Eventual consistency acceptable |
| Alert notification | Async (Kafka → webhook) | Best-effort delivery |

**Decision rule:** If the user is waiting AND the operation takes < 2 seconds → sync. Otherwise → async with a job ID the user can poll.

**Interview:** "Our sync/async boundary is driven by user experience. Anything where a user is waiting and it can complete in under 2 seconds is synchronous. Document processing, evaluation, and report generation are asynchronous via Kafka. We return a job ID that the frontend polls for status updates."

---

### AREA 17: Event-Driven Design

**Where:** Kafka as the event backbone
**How:**

**Kafka Topics:**

| Topic | Producer | Consumer(s) | Event Types |
|-------|----------|------------|-------------|
| `document.lifecycle` | Ingestion | Retrieval, Evaluation, FinOps | uploaded, parsed, chunked, embedded, indexed, deleted |
| `query.lifecycle` | API GW, Inference | Evaluation, FinOps, Observability | received, retrieved, generated, delivered, flagged |
| `tenant.lifecycle` | Identity | All services | created, updated, suspended, deleted |
| `policy.changes` | Governance | All services | policy_updated, flag_toggled |
| `cost.events` | FinOps | Observability, Governance | budget_warning, budget_exceeded |
| `eval.results` | Evaluation | Governance, Observability | eval_completed, regression_detected |
| `audit.events` | All services | Governance | any state change, admin action |

**Event Schema (CloudEvents-compatible):**
```json
{
  "id": "uuid-v4",
  "source": "ingestion-svc",
  "type": "document.indexed",
  "specversion": "1.0",
  "time": "2026-04-23T10:30:00Z",
  "datacontenttype": "application/json",
  "subject": "doc-uuid",
  "tenantid": "tenant-uuid",
  "correlationid": "req-uuid",
  "data": {
    "document_id": "doc-uuid",
    "chunks_count": 42,
    "embedding_model": "nomic-embed-text",
    "processing_time_ms": 3200
  }
}
```

**Interview:** "We use Kafka as our event backbone with CloudEvents-compatible schema. Events are immutable, versioned, and self-describing. Every event carries a correlation ID for distributed tracing and a tenant ID for isolation. Events drive the async pipeline — when a document is chunked, an event triggers embedding; when embedding completes, an event triggers indexing."

---

### AREA 18: Workflow Orchestration

**Where:** Ingestion Service (saga coordinator) + Kafka
**How:**
The document processing pipeline is an orchestrated saga:

```
Saga: Document Processing
  Step 1: Parse document → extract text
    Compensate: delete parsed output
  Step 2: Chunk text → create chunks
    Compensate: delete chunks from PostgreSQL
  Step 3: Generate embeddings → batch embed chunks
    Compensate: delete vectors from Qdrant
  Step 4: Build knowledge graph → extract entities/relations
    Compensate: delete nodes from Neo4j
  Step 5: Index → mark document as ACTIVE
    Compensate: mark document as FAILED
```

- **Orchestrator pattern** (not choreography): Ingestion Service coordinates steps
- Each step publishes a completion event; orchestrator listens and triggers next step
- On failure at any step: orchestrator runs compensation steps in reverse order
- Saga state stored in PostgreSQL (`sagas` table) with step progress

**Interview:** "We use the orchestrator saga pattern for document processing. The Ingestion Service coordinates a 5-step pipeline: parse, chunk, embed, graph-build, index. Each step has a compensating action. If embedding fails, the orchestrator runs compensations in reverse — deleting chunks from PostgreSQL and parsed output from storage. Saga state is persisted so we can resume after crashes."

---

### AREA 19: Compensation Logic

**Where:** Each service implements compensating actions for its operations
**How:**

| Service | Action | Compensation |
|---------|--------|-------------|
| Ingestion | Store parsed text in blob storage | Delete blob |
| Ingestion | Insert chunks into PostgreSQL | DELETE FROM chunks WHERE document_id = ? |
| Ingestion | Insert vectors into Qdrant | Delete points by document_id filter |
| Ingestion | Insert entities into Neo4j | MATCH (n {document_id: $id}) DETACH DELETE n |
| FinOps | Credit tokens to usage | Reverse credit (debit) |
| Identity | Create tenant | Soft-delete tenant + cleanup cascade |

- Compensations are idempotent (running twice produces same result)
- Compensation failures are logged and alerted — manual intervention required
- Compensation timeout: 30 seconds per step

**Interview:** "Every saga step has an idempotent compensating action. If we fail at step 3 (embedding), we compensate step 2 by deleting chunks from PostgreSQL and step 1 by deleting the parsed blob. Compensations are idempotent — running them twice is safe. If a compensation itself fails, we alert for manual intervention."

---

### AREA 20: Idempotency Strategy

**Where:** API Gateway + every service
**How:**

- **API level:** Write endpoints accept `X-Idempotency-Key` header. Gateway stores key → response mapping in Redis (TTL: 24h). Duplicate request returns cached response
- **Kafka consumers:** Every consumer tracks processed event IDs in a `processed_events` table. Before processing, check if event ID exists → skip if already processed
- **Database writes:** Use INSERT ... ON CONFLICT DO NOTHING for creation. Use version column for updates (optimistic locking)
- **Embedding generation:** Hash chunk content → if embedding for that hash exists in Qdrant, skip

```python
# Kafka consumer idempotency
def process_event(event):
    event_id = event.headers["id"]
    if event_repo.exists(event_id):
        logger.info(f"Skipping duplicate event {event_id}")
        return
    try:
        do_work(event)
        event_repo.mark_processed(event_id)
    except Exception:
        # Don't mark as processed — will be retried
        raise
```

**Interview:** "Idempotency is enforced at every layer. The API Gateway uses X-Idempotency-Key headers with Redis-backed deduplication. Kafka consumers track processed event IDs in a deduplication table. Database inserts use ON CONFLICT DO NOTHING. Embeddings are content-hashed — if the same chunk content is seen again, we skip re-embedding."

---

### AREA 21: Service Decomposition

**Where:** The 10 microservices themselves
**How:**

**Decomposition criteria applied:**

| Criterion | How Applied |
|-----------|------------|
| Single Responsibility | Each service owns one bounded context |
| Independent Deployment | Any service can be redeployed without affecting others |
| Independent Scaling | Ingestion scales with upload volume, Retrieval with query volume |
| Team Ownership | Each service could be owned by a different team |
| Data Ownership | Database-per-service pattern |
| Technology Heterogeneity | Go services for I/O-bound, Python for ML-bound |
| Failure Isolation | One service's crash doesn't cascade (circuit breaker + bulkhead) |

**Why Go vs Python:**
- **Go:** API Gateway (high concurrency, low latency), Identity (JWT/crypto), Governance (policy engine), FinOps (aggregation), Observability (metrics collection) — all I/O-bound, benefit from goroutines
- **Python:** Ingestion (ML libraries — tiktoken, sentence-transformers), Retrieval (qdrant-client, neo4j), Inference (ollama, langchain), Evaluation (sklearn, ragas) — all ML-bound, benefit from Python ecosystem

**Interview:** "We decomposed by bounded context and scaling needs. Go for I/O-bound services that need high concurrency (gateway handles thousands of concurrent connections via goroutines). Python for ML-bound services that need the rich ML ecosystem (tiktoken for tokenization, sentence-transformers for embeddings, ragas for evaluation). Each service is independently deployable and scalable."

---

### AREAS 22-29: Service Specifications

(Detailed per-service specs follow)

---

### AREA 22: Identity Service (Go)

**Responsibilities:**
- Tenant CRUD (create, read, update, suspend, delete)
- User CRUD with tenant association
- Role management (RBAC): `platform_admin`, `tenant_admin`, `tenant_user`, `evaluator`, `viewer`
- JWT issuance and validation (RS256, 15-minute access token, 7-day refresh token)
- API key management (for programmatic access)
- Login/logout + session creation in Redis

**API Surface (gRPC + REST via gateway):**
```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/tenants
POST   /api/v1/tenants
GET    /api/v1/tenants/{id}/users
POST   /api/v1/tenants/{id}/users
PUT    /api/v1/tenants/{id}/users/{uid}/roles
POST   /api/v1/tenants/{id}/api-keys
DELETE /api/v1/tenants/{id}/api-keys/{kid}
```

**Database:** PostgreSQL `identity` schema — `tenants`, `users`, `roles`, `api_keys` tables

---

### AREA 23: Knowledge Ingestion Service (Python)

**Responsibilities:**
- Accept document uploads (PDF, DOCX, TXT, HTML, Markdown)
- Parse documents (PyMuPDF for PDF, python-docx for DOCX, BeautifulSoup for HTML)
- Chunk text (recursive character splitter, configurable chunk_size and overlap)
- Generate embeddings via Ollama embed API (nomic-embed-text or mxbai-embed-large)
- Extract entities and relationships for knowledge graph (NER + relation extraction via LLM)
- Orchestrate the ingestion saga (parse → chunk → embed → graph → index)
- Track document lifecycle state machine

**API Surface:**
```
POST   /api/v1/documents/upload          (multipart file upload)
GET    /api/v1/documents                  (list with pagination)
GET    /api/v1/documents/{id}             (status + metadata)
GET    /api/v1/documents/{id}/chunks      (list chunks)
DELETE /api/v1/documents/{id}             (trigger deletion saga)
POST   /api/v1/documents/{id}/reprocess   (re-run pipeline)
```

**Kafka produces:** `document.lifecycle` events
**Kafka consumes:** `policy.changes` (for chunking strategy updates)

**Database:** PostgreSQL `ingestion` schema — `documents`, `chunks`, `processing_jobs` tables + writes to Qdrant + Neo4j

---

### AREA 24: Retrieval Service (Python)

**Responsibilities:**
- Accept search queries
- Execute hybrid retrieval: vector search (Qdrant) + graph traversal (Neo4j) + metadata filter (PostgreSQL)
- Rerank results using cross-encoder model or reciprocal rank fusion (RRF)
- Cache query results in Redis
- Return top-K chunks with relevance scores and source citations

**API Surface (internal gRPC, called by Inference Service):**
```
POST /internal/v1/retrieve  {query, tenant_id, top_k, filters}
→ {chunks: [{id, text, score, source_doc, page_num, entity_context}]}
```

**Retrieval Strategy:**
```python
def hybrid_retrieve(query, tenant_id, top_k=10):
    # 1. Vector search (semantic similarity)
    vector_results = qdrant.search(
        collection="chunks",
        query_vector=embed(query),
        query_filter={"tenant_id": tenant_id},
        limit=top_k * 2
    )

    # 2. Graph search (entity-based traversal)
    entities = extract_entities(query)
    graph_results = neo4j.query("""
        MATCH (e:Entity {tenant_id: $tid})-[:MENTIONED_IN]->(c:Chunk)
        WHERE e.name IN $entities
        RETURN c, count(e) as relevance
        ORDER BY relevance DESC LIMIT $limit
    """, tid=tenant_id, entities=entities, limit=top_k)

    # 3. Merge + Rerank (reciprocal rank fusion)
    merged = reciprocal_rank_fusion(vector_results, graph_results)
    return merged[:top_k]
```

---

### AREA 25: Inference Service (Python)

**Responsibilities:**
- Receive retrieved chunks from Retrieval Service
- Construct prompts with system instructions, context chunks, and user query
- Call Ollama API for LLM generation
- Stream responses to the client (SSE or gRPC streaming)
- Apply output guardrails (PII detection, toxicity check, hallucination detection)
- Track token usage and report to FinOps

**Key Design:**
```python
def generate_answer(query, chunks, model="llama3"):
    # 1. Construct prompt
    context = "\n\n".join([f"[Source: {c.source}, Page {c.page}]\n{c.text}" for c in chunks])
    prompt = f"""Answer the question based ONLY on the provided context.
    If the context doesn't contain the answer, say "I don't have enough information."
    Always cite your sources using [Source: filename, Page N].

    Context:
    {context}

    Question: {query}

    Answer:"""

    # 2. Call Ollama (with circuit breaker)
    response = ollama_circuit_breaker.call(
        ollama.generate, model=model, prompt=prompt, stream=True
    )

    # 3. Apply guardrails
    validated = guardrails.check(response)

    # 4. Report token usage to FinOps
    kafka.produce("cost.events", {
        "tokens_prompt": count_tokens(prompt),
        "tokens_completion": count_tokens(response),
        "model": model
    })

    return validated
```

---

### AREA 26: Evaluation Service (Python)

**Responsibilities:**
- Manage evaluation datasets (question + ground truth answer + expected source documents)
- Run offline evaluations (batch — nightly or on-demand)
- Run online evaluations (sample production queries, compare to baselines)
- Compute metrics: faithfulness, answer relevance, context precision, context recall, MRR, NDCG
- Detect regressions and block deployments via regression gate
- Track eval results over time for trend analysis

**Metrics Computed:**

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| Context Precision@5 | Are retrieved chunks relevant? | > 0.8 |
| Context Recall | Did we retrieve all relevant chunks? | > 0.7 |
| MRR (Mean Reciprocal Rank) | Is the most relevant chunk ranked first? | > 0.6 |
| Faithfulness | Is the answer grounded in context? (no hallucination) | > 0.9 |
| Answer Relevance | Does the answer address the question? | > 0.8 |
| Answer Similarity | Does the answer match ground truth? | > 0.7 |

---

### AREA 27: Governance Service (Go)

**Responsibilities:**
- Policy engine: define and evaluate rules (e.g., "flag answers with confidence < 0.6")
- Human-in-the-loop (HITL) queue: flagged answers routed to human reviewers
- Audit log: immutable append-only log of all system actions
- Compliance reporting: who accessed what, when, why
- Feature flags: enable/disable features per tenant
- Model selection policy: which tenant uses which model

**Policy-as-Code:**
```go
// Policy rule engine (simplified)
type PolicyRule struct {
    ID        string
    Name      string
    Condition string   // CEL expression
    Action    string   // "flag", "block", "log", "notify"
    Severity  string   // "critical", "high", "medium", "low"
}

// Example rules:
// 1. Flag low confidence: "response.confidence < 0.6" → flag for HITL
// 2. Block PII: "response.contains_pii == true" → block response
// 3. Alert cost spike: "request.token_cost > 0.50" → notify
```

---

### AREA 28: Observability Service (Go)

**Responsibilities:**
- Aggregate Prometheus metrics from all services
- Define and evaluate SLO targets
- Manage alerting rules
- Provide dashboard data for admin UI
- Track distributed traces (integrate with Jaeger)
- System health endpoint aggregation

**SLOs Defined:**

| SLO | Target | Measurement |
|-----|--------|-------------|
| Query latency p95 | < 3 seconds | Prometheus histogram |
| Ingestion throughput | > 10 docs/minute | Counter rate |
| System availability | 99.5% | Uptime checks |
| Retrieval precision | > 80% | Evaluation Service metrics |
| Error rate | < 1% | 5xx counter / total |

---

### AREA 29: FinOps / Billing Service (Go)

**Responsibilities:**
- Track token usage per request (prompt + completion)
- Attribute cost to tenant
- Set and enforce per-tenant budgets (daily, monthly)
- Alert at budget thresholds (50%, 80%, 100%)
- Usage analytics (cost per query, cost per document ingestion)
- Billing report generation

**Cost Model:**
```
Cost per request = (prompt_tokens * input_price) + (completion_tokens * output_price)

For Ollama (local): actual cost = 0 (but we track "shadow cost" as if using cloud API
  to help tenants understand what they'd pay at scale)

Shadow pricing:
  Llama 3 (8B):  input=$0.0001/1K tokens, output=$0.0003/1K tokens
  Mistral (7B):  input=$0.0001/1K tokens, output=$0.0002/1K tokens
```

---

### AREA 30: API Contract Strategy

**Where:** All services
**How:**
- **External APIs:** REST (JSON over HTTP/2) via API Gateway, documented with OpenAPI 3.1
- **Internal APIs:** gRPC with Protocol Buffers (strongly typed, code-generated clients)
- **Contract versioning:** URL-based (`/api/v1/`, `/api/v2/`)
- **Breaking change policy:** New version required for: removing fields, changing types, changing semantics. Additive changes (new optional fields) allowed in-place
- **Contract testing:** Consumer-driven contract tests (Pact or similar)

```protobuf
// retrieval.proto
syntax = "proto3";
package documind.retrieval.v1;

service RetrievalService {
  rpc Retrieve(RetrieveRequest) returns (RetrieveResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}

message RetrieveRequest {
  string query = 1;
  string tenant_id = 2;
  int32 top_k = 3;
  map<string, string> filters = 4;
}

message RetrieveResponse {
  repeated Chunk chunks = 1;
  float latency_ms = 2;
  string retrieval_strategy = 3;
}
```

**Interview:** "External APIs are REST for frontend compatibility, internal APIs are gRPC for type safety and performance. We version URLs for breaking changes and use Protocol Buffers for code-generated clients. Contract tests verify that service changes don't break consumers."

---

### AREA 31: Event Contract Strategy

**Where:** Kafka events
**How:**
- All events follow CloudEvents specification (v1.0)
- Event schema stored in a schema registry (local JSON Schema files in `schemas/events/`)
- Schema versioning: `type` field includes version (e.g., `document.indexed.v1`)
- **Evolution rules:** New optional fields are non-breaking. Removing fields or changing types requires new version
- Producer validates event against schema before publishing
- Consumer validates event on receipt

**Interview:** "Events follow CloudEvents spec. Schemas are versioned — `document.indexed.v1` can evolve to `v2` with a new schema. Producers validate outgoing events, consumers validate incoming events. This prevents silent contract violations."

---

### AREA 32: Prompt Contract Strategy

**Where:** Inference Service
**How:**
- Prompts are versioned templates stored in PostgreSQL `prompts` table
- Each prompt template has: `id`, `version`, `template_text`, `variables`, `model`, `max_tokens`, `temperature`
- Prompt changes go through a review process (governance approval for production prompts)
- A/B testing: multiple prompt versions can be active simultaneously with traffic splitting
- Prompt lineage: every response tracks which prompt version generated it

```
prompts table:
  id: uuid
  name: "rag_answer_v3"
  version: 3
  template: "Answer based ONLY on context..."
  variables: ["context", "query"]
  model: "llama3"
  temperature: 0.1
  max_tokens: 1024
  status: "active" | "draft" | "deprecated"
  created_by: user_id
  approved_by: user_id
  created_at: timestamp
```

**Interview:** "Prompts are versioned artifacts — just like code. Each prompt template is stored in PostgreSQL with version, model, temperature, and approval status. Every LLM response records which prompt version generated it, so we can trace quality regressions to specific prompt changes."

---

### AREA 33: Output Contract Strategy

**Where:** Inference Service + API Gateway
**How:**
- Every LLM response is validated against an output schema before returning to the user
- Output schema defines: required fields (answer, citations, confidence), forbidden patterns (PII, toxic content)
- Output validation pipeline:
  1. Schema validation (required fields present)
  2. Citation validation (cited sources exist in retrieved chunks)
  3. PII scan (regex + NER-based detection)
  4. Confidence scoring (based on retrieval scores + model logprobs if available)
  5. Length validation (min/max answer length)

```python
class OutputContract:
    def validate(self, response):
        errors = []
        if not response.answer:
            errors.append("Empty answer")
        if not response.citations:
            errors.append("No citations provided")
        if response.confidence < 0.0 or response.confidence > 1.0:
            errors.append("Invalid confidence score")
        if self.pii_detector.scan(response.answer):
            errors.append("PII detected in answer")
        if len(response.answer) > self.max_length:
            errors.append("Answer exceeds max length")
        return errors
```

---

### AREA 34: Retrieval Schema

**Where:** Retrieval Service
**How:**
- Standardized schema for retrieval results across all search backends:

```python
@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    tenant_id: str
    text: str
    score: float            # 0.0 to 1.0, normalized
    source: str             # source backend: "vector", "graph", "metadata"
    metadata: dict          # {filename, page_num, section, heading}
    entity_context: list    # related entities from graph
    retrieval_strategy: str # "hybrid", "vector_only", "graph_only"
    latency_ms: float
```

- All search backends (Qdrant, Neo4j, PostgreSQL) return results normalized to this schema
- Reranker operates on this standardized format
- Schema is defined as a Protocol Buffer for gRPC and Pydantic model for REST

---

### AREA 35: Knowledge Lifecycle

**Where:** Ingestion Service + Governance Service
**How:**

```
Knowledge Lifecycle:
  SOURCE → INGEST → CHUNK → EMBED → INDEX → ACTIVE → STALE → RE-INGEST or ARCHIVE
                                                 │
                                              DELETED
```

| Stage | Trigger | Action |
|-------|---------|--------|
| SOURCE | User uploads or URL crawl | Store raw file in MinIO/local storage |
| INGEST | Upload event | Parse → extract text |
| CHUNK | Parse complete | Split into chunks with metadata |
| EMBED | Chunk complete | Generate vector embeddings |
| INDEX | Embed complete | Write to Qdrant + Neo4j |
| ACTIVE | Index complete | Searchable by users |
| STALE | Source document updated, or TTL expired | Mark for re-ingestion |
| RE-INGEST | Stale detection | Re-run pipeline, replace old vectors/nodes |
| ARCHIVE | Admin action or retention policy | Remove from search index, keep metadata |
| DELETED | Admin action | Purge all data (vectors, graph, metadata, raw file) |

- **Staleness detection:** Configurable per tenant. Options: TTL-based (re-check source every N days), hash-based (detect source content change), manual trigger
- **Retention policy:** Configurable per tenant (e.g., auto-archive after 365 days)

**Interview:** "Knowledge has a lifecycle from source to deletion. We track staleness via content hashing — if the source document changes, the system detects it and triggers re-ingestion. Old vectors are replaced atomically. Retention policies auto-archive old knowledge to keep the search index relevant."

---

### AREA 36: Source Trust Model

**Where:** Ingestion Service + Governance Service
**How:**
- Each document source has a trust level: `verified`, `trusted`, `unverified`, `untrusted`
- Trust level affects retrieval ranking (verified sources ranked higher)
- Trust level affects governance (unverified sources flagged for review)
- Source verification: admin manually verifies, or automated checks (domain allowlist, checksum verification)

| Trust Level | Retrieval Boost | Governance Action |
|-------------|----------------|-------------------|
| Verified | 1.5x score multiplier | Auto-serve answers |
| Trusted | 1.0x (no change) | Auto-serve answers |
| Unverified | 0.8x score reduction | Flag if sole source |
| Untrusted | 0.5x score reduction | Always flag for HITL |

---

### AREA 37: Historical Knowledge Policy

**Where:** Governance Service + Retrieval Service
**How:**
- Historical documents (superseded by newer versions) are not deleted but demoted in ranking
- Retrieval Service supports `temporal_filter`: `latest_only`, `include_historical`, `as_of_date`
- Default behavior: return latest knowledge only
- Use case: legal/compliance queries may need historical knowledge ("What did the policy say in 2024?")
- Version chains: documents linked to their predecessors via `previous_version_id`

---

### AREA 38: Index Lifecycle

**Where:** Ingestion Service + Qdrant + Neo4j
**How:**
- **Qdrant collections:** One collection per tenant (or shared with tenant_id filter — configurable)
- **Index rebuilds:** Triggered by embedding model change, chunk strategy change, or data corruption
- **Rolling rebuild:** Create new collection, index in background, swap alias, delete old collection (zero-downtime)
- **Index health checks:** Periodic validation — sample queries + known-good results, compare scores
- **Compaction:** Qdrant handles vector compaction internally. Neo4j: periodic MATCH cleanup of orphan nodes

---

### AREA 39: Embedding Lifecycle

**Where:** Ingestion Service
**How:**
- Embedding model tracked per chunk: `embedding_model`, `embedding_version`, `embedding_date`
- **Model change:** When switching embedding models (e.g., nomic-embed-text → mxbai-embed-large):
  1. New documents use new model immediately
  2. Background job re-embeds existing chunks with new model
  3. During migration: both old and new embeddings exist, query uses appropriate model
  4. After migration complete: delete old embeddings
- **Dimensionality tracking:** Each model has known dimensionality (e.g., 768, 1024). Collection schema enforced
- **Embedding drift detection:** Periodic check — embed same reference texts, compare to baseline vectors. Significant drift → alert

**Interview:** "Embedding models are versioned per chunk. When we change models, we run a background re-embedding job while maintaining both old and new vectors. Queries use the matching model's embeddings. This enables zero-downtime embedding model upgrades."

---

### AREA 40: Cache Architecture

**Where:** Redis (centralized cache)
**How:**

| Cache Layer | Key Pattern | TTL | Purpose |
|-------------|-------------|-----|---------|
| Query result cache | `tenant:{tid}:query:{hash}` | 5 min | Avoid re-running retrieval + inference |
| Embedding cache | `embed:{model}:{content_hash}` | 24h | Avoid re-embedding identical content |
| Tenant config cache | `tenant:{tid}:config` | 1 min | Avoid DB reads for every request |
| Policy cache | `policies:active` | 30s | Fast policy evaluation without DB read |
| Session cache | `session:{sid}` | 30 min | User session data |
| Rate limit counters | `ratelimit:{tid}:{endpoint}:{window}` | window duration | Sliding window counters |

**Cache-aside pattern:**
```python
def get_with_cache(key, ttl, fetch_fn):
    cached = redis.get(key)
    if cached:
        return deserialize(cached)
    result = fetch_fn()
    redis.setex(key, ttl, serialize(result))
    return result
```

---

### AREA 41: Cache Consistency

**Where:** Redis + Kafka events
**How:**
- **TTL-based expiry:** Most caches expire naturally (5 min for queries, 30s for policies)
- **Event-driven invalidation:** When a document is re-indexed, Kafka event triggers cache invalidation for all queries that referenced that document
- **Write-through for config:** Tenant config changes write to DB + Redis simultaneously
- **Cache stampede prevention:** Use Redis `SET NX` with short TTL as a lock. Only one request fetches on cache miss; others wait or get stale data
- **No cache for writes:** Write operations never read from cache

```python
# Event-driven cache invalidation
@kafka_consumer("document.lifecycle")
def handle_document_event(event):
    if event.type in ("document.reindexed", "document.deleted"):
        tenant_id = event.data["tenant_id"]
        doc_id = event.data["document_id"]
        # Invalidate all query caches for this tenant that might reference this doc
        pattern = f"tenant:{tenant_id}:query:*"
        invalidate_by_pattern(pattern)
```

---

### AREA 42: Tenant-Aware Cache

**Where:** Redis
**How:**
- Every cache key is namespaced by `tenant_id` — cross-tenant cache hits are impossible
- Tenant-specific TTLs: premium tenants get longer cache TTL, free tier gets shorter
- Tenant-specific cache size limits: eviction per tenant (not global LRU that could starve small tenants)
- Cache metrics tracked per tenant: hit rate, miss rate, eviction rate
- Tenant suspension: bulk invalidate all cache keys for suspended tenant

**Interview:** "Our cache is fully tenant-aware. Every key is namespaced by tenant ID, so cross-tenant leakage is structurally impossible. We track cache hit rates per tenant and enforce per-tenant size limits so one tenant's workload can't evict another's cached data."

---

### AREA 43: Capacity Model

**Where:** Observability Service
**How:**
- Track resource utilization per service: CPU, memory, disk, network, GPU (for Ollama)
- Capacity dimensions:

| Dimension | Metric | Current Limit | Scale Trigger |
|-----------|--------|--------------|---------------|
| Query throughput | queries/sec | 50 qps | > 40 qps → scale Retrieval pods |
| Ingestion throughput | docs/min | 20 docs/min | > 15 → scale Ingestion consumers |
| Ollama inference | requests/sec | 5 rps | > 4 → add GPU pod replica |
| Vector DB storage | vectors count | 10M | > 8M → shard collection |
| Graph DB nodes | node count | 1M | > 800K → optimize queries first |
| Cache memory | Redis memory | 1GB | > 800MB → evict or scale |

- **Capacity planning dashboard:** Shows current utilization % against limits, projected growth
- **Auto-scaling:** Kubernetes HPA based on custom metrics (not just CPU)

---

### AREA 44: Queue Strategy

**Where:** Kafka
**How:**

| Queue (Topic) | Partitions | Consumer Groups | Ordering Guarantee |
|---------------|------------|-----------------|-------------------|
| `document.lifecycle` | 6 | ingestion-workers, retrieval-sync, finops-tracker | Per-partition (key = document_id) |
| `query.lifecycle` | 12 | eval-sampler, finops-tracker, audit-writer | Per-partition (key = tenant_id) |
| `cost.events` | 3 | finops-aggregator | Per-partition (key = tenant_id) |
| `policy.changes` | 1 | all-services | Total order (single partition) |
| `audit.events` | 6 | governance-writer | Per-partition (key = tenant_id) |

- **Dead letter queue (DLQ):** Each topic has a `*.dlq` topic for messages that fail after 3 retries
- **Retention:** 7 days for all topics, 30 days for audit events
- **Compaction:** `policy.changes` uses log compaction (keep latest value per key)

---

### AREA 45: Backpressure Strategy

**Where:** API Gateway + Kafka consumers + Ingestion Service
**How:**
- **API Gateway:** Rate limiting per tenant (see Area 29). When rate exceeded → HTTP 429 with `Retry-After` header
- **Kafka consumers:** Max in-flight messages per consumer (`max.poll.records=10`). If processing is slow, consumer automatically throttles polling
- **Ingestion Service:** Max concurrent processing jobs per tenant (default: 5). Additional uploads queued in PostgreSQL `pending_jobs` table
- **Ollama:** Max concurrent requests (3). If all slots busy, Inference Service returns "service busy, retry" or queues with timeout
- **Circuit breaker:** When Ollama is overloaded, circuit opens → immediate rejection with fallback message ("System is processing many requests, please try again shortly")

```
Backpressure chain:
  User → API GW (rate limit) → Kafka (consumer throttle) → Service (concurrency limit) → Ollama (circuit breaker)
```

**Interview:** "Backpressure propagates through the system. The API Gateway rate-limits per tenant. Kafka consumers self-throttle via max.poll.records. Services enforce concurrency limits. Ollama calls use a circuit breaker. At every layer, the system degrades gracefully rather than accepting unbounded load."

---

### AREA 46: Database Strategy

**Where:** PostgreSQL (primary relational store)
**How:**
- **Schema-per-service:** Each service owns its own PostgreSQL schema (namespace). No cross-schema joins
  ```
  identity.tenants, identity.users, identity.roles
  ingestion.documents, ingestion.chunks, ingestion.processing_jobs
  eval.datasets, eval.results, eval.metrics
  governance.policies, governance.audit_log, governance.hitl_queue
  finops.usage, finops.budgets, finops.billing
  observability.alerts, observability.slo_targets
  ```
- **Connection pooling:** PgBouncer per service (Go services use pgxpool, Python services use asyncpg pool)
- **Migrations:** Numbered SQL scripts per schema, tracked in `_migrations` table
- **Row-level security:** Tenant isolation enforced at database level (see Area 5)
- **WAL mode:** Enabled for all connections
- **Indexes:** On every WHERE/ORDER BY/JOIN column
- **Backup:** pg_dump daily (Kind volume snapshot)

---

### AREA 47: Vector DB Strategy

**Where:** Qdrant
**How:**
- **Collection design:** One collection `chunks` with tenant_id as payload field
- **Vector config:** HNSW index, cosine similarity, vector size matches embedding model
- **Sharding:** Single-node for local dev. In production: distributed mode with 3 nodes
- **Payload indexes:** `tenant_id` (keyword), `document_id` (keyword), `created_at` (integer)
- **Quantization:** Scalar quantization enabled for memory efficiency on large collections
- **Snapshot/backup:** Qdrant snapshot API, triggered after bulk ingestion

```python
# Qdrant collection creation
client.create_collection(
    collection_name="chunks",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
    quantization_config=ScalarQuantization(
        scalar=ScalarQuantizationConfig(type=ScalarType.INT8, quantile=0.99)
    ),
)
```

---

### AREA 48: Graph Strategy

**Where:** Neo4j
**How:**
- **Node types:** `Entity` (named entities extracted from documents), `Chunk` (text chunks), `Document` (source documents), `Concept` (taxonomy/ontology terms)
- **Relationship types:** `MENTIONED_IN` (Entity → Chunk), `PART_OF` (Chunk → Document), `RELATED_TO` (Entity → Entity), `IS_A` (Concept → Concept)
- **Ontology:** Defined per tenant in the Governance Service. Example: for a legal tenant, concepts like "Contract → Clause → Obligation"
- **Graph queries:** Used for multi-hop reasoning. "What are all clauses related to indemnification in contracts from vendor X?"

```cypher
// Multi-hop retrieval
MATCH (e:Entity {name: $entity, tenant_id: $tid})
      -[:RELATED_TO*1..3]-(related:Entity)
      -[:MENTIONED_IN]->(c:Chunk)
RETURN c.text, c.document_id, c.score
ORDER BY c.score DESC
LIMIT $top_k
```

---

### AREA 49: HA Strategy

**Where:** Kubernetes + Istio
**How:**
- **Pod replicas:** Every service runs with at least 2 replicas (anti-affinity rules spread across nodes)
- **Health checks:** Liveness probe (is the process alive?) + Readiness probe (can it serve traffic?)
- **Graceful shutdown:** Services handle SIGTERM, drain in-flight requests (30s grace period)
- **Data store HA:** PostgreSQL with streaming replication (primary + standby), Qdrant with replication factor 2, Redis Sentinel
- **Istio retry:** Automatic retry on 5xx (max 2 retries, 100ms between)
- **Zero-downtime deployment:** Rolling updates with maxUnavailable: 0, maxSurge: 1

---

### AREA 50: DR Strategy

**Where:** Backup + restore procedures
**How:**

| Component | RPO | RTO | Backup Method |
|-----------|-----|-----|---------------|
| PostgreSQL | 15 min | 30 min | WAL archiving + daily pg_dump |
| Qdrant | 1 hour | 1 hour | Snapshots after bulk ops |
| Neo4j | 1 hour | 1 hour | neo4j-admin dump |
| Redis | N/A (cache) | 5 min | Rebuild from source of truth |
| Kafka | 0 (replicated) | 5 min | Topic replication factor 3 |
| Raw documents | 0 | 15 min | MinIO/local volume with replication |

- **DR runbook:** Step-by-step procedure documented in `docs/DR_RUNBOOK.md`
- **DR drills:** Monthly restore test from backup
- For local Kind: volume snapshots + restore scripts

---

### AREA 51: Multi-Region Strategy

**Where:** Design documentation (not implemented locally, but designed)
**How:**
- **Active-passive:** Primary region serves all traffic. Secondary region receives replicated data. Failover via DNS switch
- **Data replication:** PostgreSQL logical replication, Qdrant collection replication, Kafka MirrorMaker
- **Tenant affinity:** Each tenant assigned to a primary region. Requests routed by tenant_id

**Note:** This is a design-only area for local Kind deployment. You implement the abstractions (region-aware config, data replication interfaces) but run everything in one "region." In interviews, you explain the design and show the code abstractions.

**Interview:** "While our local deployment is single-region, the architecture supports multi-region via active-passive with tenant affinity. Each tenant is assigned a primary region. We've abstracted data replication behind interfaces — switching from local to cross-region replication is a configuration change, not a code change."

---

### AREA 52: Blast Radius Control

**Where:** Kubernetes namespaces + Istio + circuit breakers
**How:**
- **Service isolation:** Each service in its own Kubernetes Deployment with resource limits
- **Tenant isolation:** Resource quotas per tenant (enforced in FinOps)
- **Feature isolation:** New features behind feature flags, rolled out incrementally
- **Data isolation:** Schema-per-service, RLS per tenant
- **Network isolation:** Kubernetes NetworkPolicy restricts which services can talk to which

```yaml
# NetworkPolicy: Retrieval can only access Qdrant, Neo4j, PostgreSQL, Redis
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: retrieval-svc-network
spec:
  podSelector:
    matchLabels:
      app: retrieval-svc
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: qdrant
    - podSelector:
        matchLabels:
          app: neo4j
    - podSelector:
        matchLabels:
          app: postgresql
    - podSelector:
        matchLabels:
          app: redis
```

---

### AREA 53: Release Isolation

**Where:** Kubernetes + Istio traffic management
**How:**
- **Canary deployments:** New version gets 10% traffic, monitor error rate, gradually increase
  ```yaml
  apiVersion: networking.istio.io/v1beta1
  kind: VirtualService
  metadata:
    name: inference-svc
  spec:
    hosts:
    - inference-svc
    http:
    - route:
      - destination:
          host: inference-svc
          subset: stable
        weight: 90
      - destination:
          host: inference-svc
          subset: canary
        weight: 10
  ```
- **Blue-green for data stores:** Create new schema version, migrate, swap connection
- **Shadow traffic:** Istio mirror to test new version with production traffic without affecting users

---

### AREA 54: Rollback Isolation

**Where:** Kubernetes + database migrations
**How:**
- **Service rollback:** `kubectl rollout undo deployment/<service>` — instant rollback to previous version
- **Database rollback:** Every migration has a `down.sql` counterpart
- **Feature flag rollback:** Disable flag → instant behavior rollback without deployment
- **Kafka rollback:** Consumer group offset reset to replay events from a point in time
- **Rollback testing:** Every release includes a rollback test in staging

---

### AREA 55: Feature Flag Strategy

**Where:** Governance Service
**How:**
- Feature flags stored in PostgreSQL `governance.feature_flags` table
- Flags scoped by: global, per-tenant, per-user, percentage rollout
- Flag types: boolean (on/off), variant (A/B/C), percentage (0-100% rollout)
- Services fetch active flags at startup + poll every 30 seconds (cached in Redis)
- Flag lifecycle: `draft` → `active` → `deprecated` → `archived`

```python
# Feature flag check in service
class FeatureFlagClient:
    def is_enabled(self, flag_name, tenant_id=None, user_id=None):
        flag = self.get_flag(flag_name)
        if flag.scope == "global":
            return flag.enabled
        if flag.scope == "tenant" and tenant_id in flag.allowed_tenants:
            return True
        if flag.scope == "percentage":
            return hash(f"{flag_name}:{user_id}") % 100 < flag.percentage
        return flag.default_value
```

**Interview:** "Feature flags are a first-class concept in our Governance Service. Flags can be scoped globally, per-tenant, per-user, or as percentage rollouts. This gives us instant rollback without deployments and lets us test features with specific tenants before general availability."

---

### AREA 56: Policy-as-Code

**Where:** Governance Service
**How:**
- Policies written as CEL (Common Expression Language) rules stored in PostgreSQL
- Policy categories: access control, content safety, cost limits, quality gates, compliance
- Policy evaluation: synchronous for critical (content safety), async for monitoring (cost tracking)
- Policy versioning: each policy change creates a new version with changelog

```
Example policies:
1. "response.confidence < 0.6" → ACTION: flag_for_review
2. "request.tenant.monthly_tokens > request.tenant.budget" → ACTION: reject, MESSAGE: "Budget exceeded"
3. "response.contains_pii == true" → ACTION: block, LOG: "PII detected"
4. "document.source_trust == 'untrusted'" → ACTION: flag_for_review
5. "request.user.role != 'admin' && request.path.startsWith('/admin')" → ACTION: deny
```

---

### AREA 57: Human-in-the-Loop (HITL)

**Where:** Governance Service + Frontend
**How:**
- Flagged responses enter a HITL queue in PostgreSQL `governance.hitl_queue`
- Reviewers see: original question, retrieved chunks, generated answer, confidence score, flag reason
- Reviewer actions: `approve` (release to user), `reject` (delete), `edit` (modify answer), `escalate` (to senior reviewer)
- Approved/rejected decisions feed back into evaluation metrics
- SLA: flagged items must be reviewed within 1 hour (configurable per tenant)

```
HITL Flow:
  Inference → Governance check → Confidence < 0.6? → Yes → HITL Queue
                                                          ↓
                                                    Reviewer Dashboard
                                                          ↓
                                                  Approve / Reject / Edit
                                                          ↓
                                                   User gets response
                                                          ↓
                                                  Feedback → Eval metrics
```

---

### AREA 58: Feedback Architecture

**Where:** Inference Service + Evaluation Service + Kafka
**How:**
- **Explicit feedback:** User clicks thumbs up/down on answers. Stored in `eval.feedback` table
- **Implicit feedback:** Time spent reading answer, follow-up questions (indicates first answer was insufficient)
- **Feedback loop:** Negative feedback → triggers evaluation on that query → identifies if retrieval or generation was the issue
- **Feedback-to-retrain:** Aggregated feedback used to fine-tune prompt templates, adjust retrieval weights, update reranking model

```
Feedback Flow:
  User → 👍/👎 → Kafka "feedback.events"
    → Evaluation Service: compare with ground truth if available
    → Governance Service: if persistent negative feedback on a topic → flag for review
    → Inference Service: adjust prompt/model selection weights
```

---

### AREA 59: Offline Evaluation Architecture

**Where:** Evaluation Service
**How:**
- **Eval datasets:** Curated question-answer-source triples stored in `eval.datasets`
- **Eval runs:** Scheduled (nightly) or on-demand. Run all eval questions through the full RAG pipeline
- **Metrics computed:** See Area 26 metrics table
- **Comparison:** Current run vs. previous run vs. baseline. Detect regressions
- **Report generation:** HTML report with charts, drill-down per question, failure analysis
- **Storage:** Results in `eval.results`, reports in MinIO/local storage

```
Offline Eval Pipeline:
  Eval Dataset → For each (question, expected_answer, expected_sources):
    1. Run Retrieval → compare retrieved chunks vs expected_sources → precision@k, recall@k
    2. Run Inference → compare generated answer vs expected_answer → faithfulness, relevance
    3. Aggregate metrics → store in eval.results
    4. Compare with baseline → detect regressions
    5. Generate report
```

---

### AREA 60: Online Evaluation Architecture

**Where:** Evaluation Service + Kafka sampling
**How:**
- **Shadow evaluation:** Sample X% of production queries (configurable, default 5%)
- **Sampled queries** are re-evaluated async using ground truth (if available) or reference model
- **Online metrics:** Production latency, error rate, confidence distribution, token usage distribution
- **Drift detection:** Compare current confidence distribution vs. baseline. Alert if KL divergence exceeds threshold
- **A/B evaluation:** When testing new prompt versions, split traffic and compare metrics

---

### AREA 61: Regression Gate Architecture

**Where:** Evaluation Service + CI/CD pipeline
**How:**
- **Gate trigger:** Before any service deployment, run the offline eval suite
- **Gate criteria:**
  - Faithfulness must not drop > 5% from baseline
  - Context precision must not drop > 10% from baseline
  - p95 latency must not increase > 20%
  - Error rate must not increase > 1%
- **Gate enforcement:** CI/CD pipeline calls Evaluation Service API → pass/fail response
- **Override:** Platform admin can manually override a failed gate with documented reason (audit logged)

```
Deployment Pipeline:
  Code change → Build → Unit test → Integration test
    → Deploy to staging → Run eval suite → Regression gate check
      → Pass → Deploy to production (canary)
      → Fail → Block deployment + alert team
```

---

### AREA 62: Observability by Design

**Where:** All services (cross-cutting)
**How:**

**Three Pillars + Extras:**

| Pillar | Implementation | Tool |
|--------|---------------|------|
| **Metrics** | Prometheus client in every service. Custom metrics: request count, latency histogram, error count, token usage, cache hit rate | Prometheus + Grafana |
| **Logging** | Structured JSON logs with correlation_id, tenant_id, user_id, trace_id | Loki (or stdout in Kind) |
| **Tracing** | OpenTelemetry SDK in every service. Trace spans across gRPC calls, Kafka events, DB queries | Jaeger |
| **Profiling** | pprof (Go services), py-spy (Python services) — on-demand | Manual |
| **Dashboards** | Grafana dashboards per service + system overview | Grafana |

**Correlation ID flow:**
```
Frontend → API GW (generate correlation_id in header X-Correlation-ID)
  → Every service propagates it in gRPC metadata / Kafka headers
  → Every log line includes correlation_id
  → Every trace span includes correlation_id
  → One ID traces a request across all services, logs, and events
```

**Interview:** "Observability is baked in from day one, not bolted on. Every service emits Prometheus metrics, structured JSON logs with correlation IDs, and OpenTelemetry trace spans. A single correlation ID follows a request from the API Gateway through Kafka events to the database query, making debugging trivial."

---

### AREA 63: Auditability by Design

**Where:** Governance Service + all services
**How:**
- **Audit log:** Immutable append-only table `governance.audit_log`
- **What gets logged:** Every state change, every admin action, every policy evaluation, every HITL decision, every data access
- **Schema:**
  ```sql
  CREATE TABLE governance.audit_log (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      tenant_id UUID NOT NULL,
      actor_id UUID,
      actor_type VARCHAR(20),  -- 'user', 'system', 'admin', 'service'
      action VARCHAR(100),     -- 'document.uploaded', 'query.answered', 'policy.updated'
      resource_type VARCHAR(50),
      resource_id UUID,
      details JSONB,
      correlation_id UUID,
      ip_address INET,
      user_agent TEXT
  );
  CREATE INDEX idx_audit_tenant_time ON governance.audit_log(tenant_id, timestamp DESC);
  ```
- **Retention:** 1 year (configurable per compliance requirements)
- **Tamper protection:** Log entries are hash-chained (each entry includes hash of previous entry)

---

### AREA 64: SLO-Driven Design

**Where:** Observability Service
**How:**

| SLO | SLI (Indicator) | Target | Error Budget |
|-----|-----------------|--------|-------------|
| Availability | Successful responses / total | 99.5% | 3.6 hours/month |
| Query latency | p95 response time | < 3s | 5% of queries can exceed |
| Ingestion latency | Time from upload to indexed | < 5 min | 5% can exceed |
| Retrieval quality | Precision@5 from eval | > 80% | 20% of eval queries can miss |
| Answer quality | Faithfulness from eval | > 90% | 10% can miss |

- **Error budget tracking:** Observability Service tracks remaining error budget in real-time
- **Error budget policy:** When budget exhausted → freeze deployments, focus on reliability
- **SLO alerting:** Alert at 50% budget consumed (warning), 80% (critical), 100% (freeze)
- **Burn rate alerts:** If consuming budget faster than expected for the remaining month → early warning

**Interview:** "We define SLOs for availability, latency, and quality. Each has an error budget — for 99.5% availability, we can tolerate 3.6 hours of downtime per month. The Observability Service tracks burn rate in real-time. When the budget hits 80%, we freeze feature deployments and focus on reliability."

---

### AREA 65: Design-for-Change

**Where:** Architectural patterns across all services
**How:**
- **Interface-based design:** Services depend on interfaces/protocols, not implementations
  - `EmbeddingProvider` interface → currently Ollama, easily swappable to OpenAI/Cohere
  - `VectorStore` interface → currently Qdrant, swappable to Weaviate/Pinecone
  - `GraphStore` interface → currently Neo4j, swappable to ArangoDB
  - `LLMProvider` interface → currently Ollama, swappable to any OpenAI-compatible API
- **Config-driven behavior:** Chunk size, overlap, model name, temperature — all from config, not hardcoded
- **Plugin architecture for parsers:** Add new document formats (PPT, XLSX) by implementing `DocumentParser` interface
- **Schema evolution:** API versioning, event versioning, DB migration system
- **Feature flags:** Toggle behavior without deployment

```python
# Design-for-change: provider interfaces
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    def model_name(self) -> str: ...
    @abstractmethod
    def dimension(self) -> int: ...

class OllamaEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts): ...

class OpenAIEmbeddingProvider(EmbeddingProvider):  # Future swap
    def embed(self, texts): ...
```

**Interview:** "Every external dependency is behind an interface. Our EmbeddingProvider interface currently uses Ollama but can swap to OpenAI with a config change. This is design-for-change — we anticipate that LLM providers, vector databases, and embedding models will change, so we make swapping them a configuration decision, not a rewrite."

---

### AREA 66: Design-for-Debuggability

**Where:** All services
**How:**
- **Correlation ID:** Single ID traces a request across all services (see Area 62)
- **Request replay:** Any request can be replayed in a debug environment using stored request metadata
- **Debug endpoints:** Each service exposes `/debug/state` (internal only, Istio-restricted) showing:
  - Current circuit breaker states
  - Active connections
  - Cache stats
  - In-flight requests
  - Feature flag states
- **Structured error responses:** Every error includes correlation_id, error_code, human message, and debug details (in dev mode only)
- **Query explain mode:** Add `?debug=true` to any retrieval query to get: vector scores, graph traversal path, reranking scores, prompt template used, token counts
- **Log levels:** Dynamically adjustable per service without restart (via admin API)

```json
// Debug mode response
{
  "answer": "The contract expires on...",
  "debug": {
    "retrieval": {
      "vector_results": [{"chunk_id": "...", "score": 0.89}],
      "graph_results": [{"chunk_id": "...", "hops": 2}],
      "rerank_scores": [0.95, 0.87, 0.72],
      "strategy": "hybrid_rrf"
    },
    "inference": {
      "prompt_version": "rag_answer_v3",
      "model": "llama3",
      "tokens_prompt": 1240,
      "tokens_completion": 156,
      "latency_ms": 2340
    },
    "cache": "miss",
    "correlation_id": "abc-123"
  }
}
```

**Interview:** "Debug mode is built into the architecture. Any query with `?debug=true` returns the full decision path — vector scores, graph traversal path, reranking results, prompt template version, and token counts. In production, this is restricted to admins. It makes debugging retrieval quality issues trivial."

---

### AREA 67: Socio-Technical Operating Model

**Where:** Documentation + team structure design
**How:**
This area covers how TEAMS operate the system, not just code:

- **Service ownership:** Each service has an owner (team or individual). Owner is responsible for: development, deployment, on-call, SLO adherence
- **Team topology:** Platform team (owns gateway, identity, observability, FinOps) + AI team (owns ingestion, retrieval, inference, evaluation) + Governance team (owns governance, policies)
- **On-call rotation:** Defined per service. Primary + secondary responder
- **Incident response:** Runbook per service. Severity levels (SEV1-SEV4). Escalation path documented
- **Post-mortem culture:** Every SEV1/SEV2 incident gets a blameless post-mortem within 48 hours
- **Decision records:** Architecture Decision Records (ADRs) for every significant technical choice
- **Communication channels:** Per-service Slack channel (simulated). Cross-team standup for dependencies

**RACI Matrix (sample):**

| Decision | Platform Team | AI Team | Governance Team |
|----------|-------------|---------|----------------|
| API contract change | Accountable | Consulted | Informed |
| Model change | Informed | Accountable | Consulted |
| Policy change | Informed | Consulted | Accountable |
| Infrastructure change | Accountable | Informed | Informed |
| SLO definition | Accountable | Consulted | Consulted |

**Interview:** "System design isn't just technical — it's socio-technical. We define service ownership, team topologies aligned to bounded contexts, on-call rotations per service, and RACI matrices for cross-cutting decisions. The team structure mirrors the architecture — Conway's Law applied intentionally."

---

### EXTRA AREAS: MCP, Circuit Breaker, Istio

---

### EXTRA: Model Control Portal (MCP)

**Where:** Frontend (admin section) + Governance Service + Inference Service
**How:**
A dedicated admin portal for managing AI models:

**Features:**
| Feature | How |
|---------|-----|
| Model inventory | List all Ollama models with size, parameters, capabilities |
| Model assignment | Assign models to tenants (Tenant A → llama3, Tenant B → mistral) |
| Model health | Real-time metrics: latency p50/p95/p99, error rate, throughput per model |
| Model comparison | Side-by-side output comparison for same query across models |
| Model warmup | Pre-load model into GPU memory (Ollama keep_alive) |
| Token budget per model | Set max tokens/day per model per tenant |
| A/B testing | Split traffic between models, compare quality metrics |
| Model lifecycle | draft → testing → active → deprecated → retired |

**API:**
```
GET    /api/v1/admin/models                 → list available models
POST   /api/v1/admin/models/{id}/assign     → assign model to tenant
GET    /api/v1/admin/models/{id}/health     → model health metrics
POST   /api/v1/admin/models/compare         → side-by-side comparison
POST   /api/v1/admin/models/{id}/warmup     → pre-load model
```

---

### EXTRA: Circuit Breaker (Detailed)

**Where:** Inference Service (Ollama calls) + API Gateway (downstream services) + Istio (mesh-level)
**How:**

Three levels of circuit breaking:

| Level | Tool | What It Protects |
|-------|------|-----------------|
| Application | Custom Python/Go circuit breaker class | Individual external calls (Ollama, external APIs) |
| Service mesh | Istio DestinationRule outlierDetection | Inter-service communication |
| Gateway | Go middleware | Downstream service health |

**States and transitions:**
```
CLOSED ──(failure_count >= threshold)──► OPEN
  ▲                                        │
  │                                   (timeout expires)
  │                                        │
  └──(success)──── HALF_OPEN ◄────────────┘
                       │
                  (failure)
                       │
                       ▼
                     OPEN
```

**Metrics emitted:**
- `circuit_breaker_state{service="ollama"}` → gauge (0=closed, 1=half_open, 2=open)
- `circuit_breaker_failures_total{service="ollama"}` → counter
- `circuit_breaker_opens_total{service="ollama"}` → counter

**Fallback when circuit is open:**
- Inference Service: Return cached response if available, otherwise return "I'm currently unable to process your question. Please try again in a moment." with appropriate HTTP status (503)
- Never return hallucinated/fake answers as fallback

---

### EXTRA: Istio Service Mesh (Detailed)

**Where:** Kubernetes cluster
**How:**

**Istio features used:**

| Feature | Configuration | Purpose |
|---------|-------------|---------|
| mTLS | PeerAuthentication STRICT | Encrypt all service-to-service traffic |
| Traffic management | VirtualService + DestinationRule | Canary deployments, traffic shifting |
| Circuit breaking | DestinationRule outlierDetection | Eject unhealthy pods |
| Retries | VirtualService retryOn | Auto-retry on 5xx |
| Timeouts | VirtualService timeout | Prevent hanging requests |
| Rate limiting | EnvoyFilter | Per-client rate limiting |
| Observability | Kiali + Jaeger + Prometheus integration | Service mesh visualization |
| Traffic mirroring | VirtualService mirror | Shadow testing |
| Fault injection | VirtualService fault | Chaos testing |
| Authorization | AuthorizationPolicy | Service-to-service RBAC |

```yaml
# Istio PeerAuthentication — enforce mTLS everywhere
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: documind
spec:
  mtls:
    mode: STRICT

# Istio AuthorizationPolicy — only API GW can call Identity Service
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: identity-svc-policy
  namespace: documind
spec:
  selector:
    matchLabels:
      app: identity-svc
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/documind/sa/api-gateway"]
```

**Istio fault injection for chaos testing:**
```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: inference-svc-chaos
spec:
  hosts:
  - inference-svc
  http:
  - fault:
      delay:
        percentage:
          value: 10
        fixedDelay: 5s
      abort:
        percentage:
          value: 5
        httpStatus: 503
    route:
    - destination:
        host: inference-svc
```

**Interview:** "Istio gives us infrastructure-level capabilities without application code changes. mTLS encrypts all inter-service traffic. AuthorizationPolicies enforce which service can call which — the Identity Service only accepts requests from the API Gateway's service account. We use Istio's fault injection for chaos testing — randomly delaying or failing 5% of requests to verify our circuit breakers and retry logic work correctly."

---

## 4. Microservice Specifications (Summary Table)

| # | Service | Language | Database | Depends On | Depended By |
|---|---------|----------|----------|-----------|-------------|
| 1 | api-gateway | Go | Redis (rate limits) | identity-svc | Frontend, all services |
| 2 | identity-svc | Go | PostgreSQL (identity.*) | — | api-gateway, all services |
| 3 | ingestion-svc | Python | PostgreSQL (ingestion.*), Qdrant, Neo4j | identity-svc, Ollama | retrieval-svc, eval-svc |
| 4 | retrieval-svc | Python | Qdrant, Neo4j, PostgreSQL (read), Redis | ingestion-svc (data) | inference-svc |
| 5 | inference-svc | Python | Redis (cache, session) | retrieval-svc, Ollama | api-gateway |
| 6 | evaluation-svc | Python | PostgreSQL (eval.*) | retrieval-svc, inference-svc | governance-svc |
| 7 | governance-svc | Go | PostgreSQL (governance.*) | identity-svc | all services (policy reads) |
| 8 | finops-svc | Go | PostgreSQL (finops.*) | Kafka events | observability-svc, governance-svc |
| 9 | observability-svc | Go | PostgreSQL (observability.*), Prometheus | all services (metrics) | Frontend (dashboards) |
| 10 | frontend | TypeScript | — | api-gateway | Users |

---

## 5. Data Architecture

### 5.1 PostgreSQL Schemas

```
identity.*       → tenants, users, roles, api_keys, sessions
ingestion.*      → documents, chunks, processing_jobs, sagas
eval.*           → datasets, eval_questions, eval_results, feedback
governance.*     → policies, feature_flags, hitl_queue, audit_log
finops.*         → token_usage, budgets, billing_periods, cost_reports
observability.*  → alert_rules, slo_targets, incident_log
```

### 5.2 Qdrant Collections

```
chunks           → {vector: float[768], payload: {tenant_id, document_id, chunk_index, text, metadata}}
```

### 5.3 Neo4j Graph Model

```
(:Entity {name, type, tenant_id}) -[:MENTIONED_IN]-> (:Chunk {chunk_id, tenant_id})
(:Chunk) -[:PART_OF]-> (:Document {doc_id, tenant_id})
(:Entity) -[:RELATED_TO {relation_type}]-> (:Entity)
(:Concept {name, tenant_id}) -[:IS_A]-> (:Concept)
(:Entity) -[:INSTANCE_OF]-> (:Concept)
```

### 5.4 Redis Key Spaces

```
session:*                    → user sessions (TTL: 30min)
tenant:*:config              → tenant configuration cache (TTL: 1min)
tenant:*:query:*             → query result cache (TTL: 5min)
embed:*                      → embedding cache (TTL: 24h)
ratelimit:*                  → rate limit counters (TTL: window)
policies:active              → active policy rules (TTL: 30s)
circuit:*                    → circuit breaker state
```

### 5.5 Kafka Topics

```
document.lifecycle           → document state change events
query.lifecycle              → query processing events
tenant.lifecycle             → tenant management events
policy.changes               → policy/flag update events
cost.events                  → token usage and cost events
eval.results                 → evaluation result events
audit.events                 → all audit-worthy events
feedback.events              → user feedback events
*.dlq                        → dead letter queues for each topic
```

---

## 6. Infrastructure & Deployment

### 6.1 Kind Cluster

```yaml
# kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: documind
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080
    hostPort: 80
  - containerPort: 30443
    hostPort: 443
- role: worker
  extraMounts:
  - hostPath: /mnt/deepa/rag/data
    containerPath: /data
- role: worker
```

### 6.2 Namespace Layout

```
documind           → all application services
documind-data      → PostgreSQL, Qdrant, Neo4j, Redis, Kafka
documind-observ    → Prometheus, Grafana, Jaeger, Loki
istio-system       → Istio control plane
ollama             → Ollama GPU pod
```

### 6.3 Docker Compose (Dev Fallback)

For quick local development without K8s:
```yaml
# docker-compose.yml — runs all data stores + Ollama
services:
  postgresql: ...
  qdrant: ...
  neo4j: ...
  redis: ...
  kafka: ...
  zookeeper: ...
  ollama: ...
```

Individual services run natively (go run / python -m) connecting to Docker Compose data stores.

### 6.4 Makefile Commands

```makefile
cluster-up:       Create Kind cluster + install Istio
cluster-down:     Delete Kind cluster
data-up:          Deploy data stores to Kind
services-up:      Deploy all services to Kind
dev-up:           Docker Compose data stores + run services natively
test:             Run all unit + integration tests
eval:             Run evaluation suite
deploy:           Build images + deploy to Kind
canary:           Deploy canary version with 10% traffic
rollback:         Rollback to previous version
dashboard:        Open Grafana + Kiali + Jaeger
```

---

## 7. Build Sequence (Weekly Plan)

### Phase 1: Foundation (Weeks 1-2)

| Week | Focus | Services/Components |
|------|-------|-------------------|
| 1 | Project scaffold + infra | Kind cluster, Istio, Docker Compose, PostgreSQL, Redis, Makefile, proto definitions |
| 2 | Identity + API Gateway | identity-svc (Go), api-gateway (Go), JWT, RBAC, tenant management, rate limiting |

**Design areas covered:** 1 (System Boundary), 2 (Responsibility), 3 (Trust), 5 (Tenant), 6 (Control Plane), 14 (Admin Path), 22 (Identity), 30 (API Contract), 46 (Database), 49 (HA), 55 (Feature Flags)

### Phase 2: Core RAG Pipeline (Weeks 3-5)

| Week | Focus | Services/Components |
|------|-------|-------------------|
| 3 | Ingestion Service | Document parsing, chunking, embedding via Ollama, Qdrant setup |
| 4 | Retrieval Service + Neo4j | Vector search, graph search, hybrid retrieval, reranking, Neo4j setup |
| 5 | Inference Service | Prompt construction, Ollama orchestration, streaming responses, circuit breaker |

**Design areas covered:** 4 (Failure), 7 (Data Plane), 9 (State Model), 10 (Session), 13 (Read/Write Path), 16 (Sync/Async), 23 (Ingestion), 24 (Retrieval), 25 (Inference), 32 (Prompt Contract), 33 (Output Contract), 34 (Retrieval Schema), 35 (Knowledge Lifecycle), 36 (Source Trust), 38 (Index Lifecycle), 39 (Embedding Lifecycle), 40 (Cache), 47 (Vector DB), 48 (Graph), Circuit Breaker

### Phase 3: Event-Driven + Orchestration (Weeks 6-7)

| Week | Focus | Services/Components |
|------|-------|-------------------|
| 6 | Kafka setup + event-driven pipeline | Kafka deployment, event schemas, async ingestion pipeline, saga orchestration |
| 7 | Workflow + resilience | Compensation logic, idempotency, dead letter queues, backpressure, retry logic |

**Design areas covered:** 17 (Event-Driven), 18 (Workflow Orchestration), 19 (Compensation), 20 (Idempotency), 31 (Event Contract), 37 (Historical Knowledge), 41 (Cache Consistency), 42 (Tenant Cache), 44 (Queue), 45 (Backpressure)

### Phase 4: Governance + Evaluation (Weeks 8-9)

| Week | Focus | Services/Components |
|------|-------|-------------------|
| 8 | Governance Service + policies | Policy engine (CEL), HITL queue, audit log, feature flags |
| 9 | Evaluation Service + quality gates | Eval datasets, offline eval, online eval, regression gates, feedback loop |

**Design areas covered:** 11 (Agent State), 12 (Consistency), 15 (Eval Path), 26 (Evaluation), 27 (Governance), 56 (Policy-as-Code), 57 (HITL), 58 (Feedback), 59 (Offline Eval), 60 (Online Eval), 61 (Regression Gate)

### Phase 5: Observability + FinOps + Hardening (Weeks 10-11)

| Week | Focus | Services/Components |
|------|-------|-------------------|
| 10 | Observability + FinOps | Prometheus, Grafana, Jaeger, Kiali, FinOps Service, SLO tracking |
| 11 | Frontend + Model Control Portal | Next.js app, chat UI, admin dashboard, MCP portal, document viewer |

**Design areas covered:** 8 (Management Plane), 28 (Observability Svc), 29 (FinOps), 43 (Capacity Model), 62 (Observability by Design), 63 (Auditability), 64 (SLO-Driven), MCP

### Phase 6: Production Hardening (Week 12)

| Week | Focus | Services/Components |
|------|-------|-------------------|
| 12 | Deployment patterns + docs | Canary deployments, rollback, chaos testing, DR drills, Istio policies, documentation |

**Design areas covered:** 21 (Service Decomposition), 50 (DR), 51 (Multi-Region design), 52 (Blast Radius), 53 (Release Isolation), 54 (Rollback), 65 (Design-for-Change), 66 (Design-for-Debuggability), 67 (Socio-Technical), Istio (full)

---

## 8. Interview Talking Points per Design Area

### Quick Reference Card

| # | Design Area | 10-Second Interview Answer |
|---|-------------|---------------------------|
| 1 | System Boundary | "Istio Ingress + Go API Gateway. No service directly exposed. mTLS enforced." |
| 2 | Responsibility Boundary | "Database-per-service. Each service owns one bounded context. RACI matrix for cross-cutting." |
| 3 | Trust Boundary | "Four zones: untrusted (internet), DMZ (gateway), trusted (mesh), restricted (data stores)." |
| 4 | Failure Boundary | "Bulkhead (pod isolation) + circuit breaker (Istio + app-level) + graceful degradation." |
| 5 | Tenant Boundary | "PostgreSQL RLS + Qdrant payload filter + Neo4j property filter + Redis key namespace." |
| 6 | Control Plane | "Governance Service manages policies/flags. Separate from data plane. Config cached." |
| 7 | Data Plane | "Stateless services process documents and queries. State in data stores. Horizontally scalable." |
| 8 | Management Plane | "Prometheus + Grafana + Jaeger + Loki. Separate from business logic." |
| 9 | State Model | "Every entity has explicit state machine. Transitions logged. Invalid transitions rejected." |
| 10 | Session State | "Externalized to Redis. No in-memory state. Any pod serves any request." |
| 11 | Agent State | "Multi-step reasoning in Redis (hot), persisted to PostgreSQL (cold). Max steps + timeout." |
| 12 | Consistency Model | "Strong for PostgreSQL, eventual for vectors, causal for graph. Saga pattern, no 2PC." |
| 13 | Read/Write Path | "CQRS: write via async Kafka pipeline, read via sync parallel search. Independent scaling." |
| 14 | Admin Path Isolation | "Separate URL prefix, rate limits, DB pools, Istio routing. Full audit trail." |
| 15 | Eval Path Isolation | "Dedicated pods, separate schema, tagged requests. No billing, separate metrics." |
| 16 | Sync vs Async | "User-facing < 2s = sync. Everything else = async Kafka with job ID for polling." |
| 17 | Event-Driven | "Kafka backbone with CloudEvents schema. Topics per domain. DLQ for failures." |
| 18 | Workflow Orchestration | "Orchestrator saga in Ingestion Service. 5 steps with compensations. State persisted." |
| 19 | Compensation Logic | "Every saga step has idempotent compensation. Reverse order on failure. Alert on comp failure." |
| 20 | Idempotency | "X-Idempotency-Key at API, event dedup table at Kafka, ON CONFLICT at DB, content hash at embed." |
| 21 | Service Decomposition | "By bounded context + scaling needs. Go for I/O-bound, Python for ML-bound." |
| 22 | Identity Service | "Go. JWT RS256, RBAC, tenant CRUD, API keys. PostgreSQL identity schema." |
| 23 | Ingestion Service | "Python. Parse → chunk → embed → graph → index. Saga-orchestrated." |
| 24 | Retrieval Service | "Python. Hybrid vector + graph search. Reranking with RRF. Redis-cached." |
| 25 | Inference Service | "Python. Prompt construction + Ollama + guardrails + streaming. Circuit breaker." |
| 26 | Evaluation Service | "Python. Offline/online eval. Faithfulness, precision@k, MRR, NDCG. Regression gates." |
| 27 | Governance Service | "Go. CEL policy engine, HITL queue, audit log, feature flags." |
| 28 | Observability Service | "Go. Prometheus aggregation, SLO tracking, alerting rules, dashboard data." |
| 29 | FinOps Service | "Go. Token counting, cost attribution per tenant, budget enforcement, shadow pricing." |
| 30 | API Contract | "REST external (OpenAPI 3.1), gRPC internal (protobuf). URL versioning." |
| 31 | Event Contract | "CloudEvents spec. JSON Schema registry. Versioned types. Producer/consumer validation." |
| 32 | Prompt Contract | "Versioned templates in PostgreSQL. Approval workflow. A/B testing. Lineage tracking." |
| 33 | Output Contract | "Schema validation + citation check + PII scan + confidence scoring on every response." |
| 34 | Retrieval Schema | "Standardized RetrievalResult across all backends. Normalized scores." |
| 35 | Knowledge Lifecycle | "Source → Ingest → Index → Active → Stale → Re-ingest or Archive. Hash-based staleness." |
| 36 | Source Trust | "4 levels: verified/trusted/unverified/untrusted. Affects ranking and governance flags." |
| 37 | Historical Knowledge | "Superseded docs demoted, not deleted. Temporal filter for compliance queries." |
| 38 | Index Lifecycle | "Rolling rebuild for model changes. Zero-downtime via alias swap. Health checks." |
| 39 | Embedding Lifecycle | "Model versioned per chunk. Background re-embedding on model change. Drift detection." |
| 40 | Cache Architecture | "Redis. Query cache, embedding cache, config cache, rate limit counters. Cache-aside pattern." |
| 41 | Cache Consistency | "TTL-based + event-driven invalidation. Write-through for config. Stampede prevention." |
| 42 | Tenant-Aware Cache | "Key namespaced by tenant_id. Per-tenant TTL and size limits. No cross-tenant hits." |
| 43 | Capacity Model | "Per-dimension tracking. HPA with custom metrics. Projected growth dashboard." |
| 44 | Queue Strategy | "Kafka topics per domain. Partitioned by document_id or tenant_id. DLQ per topic." |
| 45 | Backpressure | "Multi-layer: API rate limit → Kafka consumer throttle → service concurrency limit → circuit breaker." |
| 46 | Database Strategy | "PostgreSQL schema-per-service. PgBouncer pooling. RLS. WAL mode. Migration system." |
| 47 | Vector DB Strategy | "Qdrant. HNSW + cosine. Scalar quantization. Payload indexes on tenant_id." |
| 48 | Graph Strategy | "Neo4j. Entity-Chunk-Document model. Ontology per tenant. Multi-hop retrieval." |
| 49 | HA Strategy | "Min 2 replicas. Anti-affinity. Liveness + readiness probes. Graceful shutdown." |
| 50 | DR Strategy | "RPO 15min (PostgreSQL WAL), RTO 30min. Monthly restore drills. Documented runbook." |
| 51 | Multi-Region | "Design-only: active-passive, tenant affinity, replication interfaces abstracted." |
| 52 | Blast Radius | "Pod isolation, tenant quotas, feature flags, NetworkPolicy, schema-per-service." |
| 53 | Release Isolation | "Istio canary (10% → 50% → 100%). Shadow traffic for testing. Blue-green for data." |
| 54 | Rollback Isolation | "kubectl rollout undo. DB down migrations. Feature flag disable. Kafka offset reset." |
| 55 | Feature Flags | "Governance Service. Scopes: global/tenant/user/percentage. Cached in Redis." |
| 56 | Policy-as-Code | "CEL rules in PostgreSQL. Categories: access, content, cost, quality, compliance." |
| 57 | HITL | "Flagged responses → HITL queue → reviewer dashboard → approve/reject/edit → feedback loop." |
| 58 | Feedback | "Explicit (thumbs up/down) + implicit (follow-ups). Feeds eval metrics + prompt tuning." |
| 59 | Offline Eval | "Nightly batch. Eval dataset through full pipeline. Metrics vs baseline." |
| 60 | Online Eval | "5% production sampling. Drift detection via KL divergence. A/B comparison." |
| 61 | Regression Gate | "Pre-deploy eval check. Block if faithfulness drops >5% or latency increases >20%." |
| 62 | Observability | "Three pillars + profiling. Correlation ID across all services, logs, traces, events." |
| 63 | Auditability | "Immutable append-only audit log. Hash-chained entries. 1-year retention." |
| 64 | SLO-Driven | "Error budgets. Burn rate alerts. Freeze deployments when budget exhausted." |
| 65 | Design-for-Change | "Interface-based. EmbeddingProvider, VectorStore, LLMProvider — swap via config." |
| 66 | Design-for-Debuggability | "Correlation ID, debug endpoints, query explain mode, dynamic log levels." |
| 67 | Socio-Technical | "Conway's Law applied. Service ownership, RACI matrix, ADRs, post-mortems." |
| E1 | MCP (Model Control Portal) | "Admin UI for model inventory, health, assignment, comparison, warmup, A/B testing." |
| E2 | Circuit Breaker | "Three levels: app-level (Python/Go class), Istio outlierDetection, gateway middleware." |
| E3 | Istio | "mTLS, traffic management, canary, fault injection, AuthorizationPolicy, Kiali viz." |

---

## 9. Irrelevant or Low-Value Areas (Transparency)

All 67 areas are relevant to this project. However, some areas will be **design-documented but lightly implemented** in a local Kind setup:

| Area | Why Light Implementation |
|------|------------------------|
| 51. Multi-Region | No second region locally. Design + interfaces implemented, not the actual replication |
| 67. Socio-Technical | This is documentation + process, not code. You write the docs and discuss in interviews |
| 43. Capacity Model | Meaningful at scale, but you implement the monitoring + alerting framework locally |
| 50. DR Strategy | Backup/restore scripts work, but DR drills are simulated |

Everything else is **fully implementable** in a local Kind + Istio setup.

---

## 10. Repository Structure

```
documind/
├── proto/                          # Protocol Buffer definitions (shared)
│   ├── retrieval/v1/retrieval.proto
│   ├── inference/v1/inference.proto
│   ├── identity/v1/identity.proto
│   └── common/v1/common.proto
├── schemas/                        # Event schemas (CloudEvents JSON Schema)
│   └── events/
│       ├── document.lifecycle.v1.json
│       ├── query.lifecycle.v1.json
│       └── ...
├── services/
│   ├── api-gateway/               # Go
│   │   ├── cmd/main.go
│   │   ├── internal/
│   │   │   ├── middleware/        # auth, rate limit, correlation ID, logging
│   │   │   ├── proxy/            # gRPC-to-REST translation
│   │   │   └── config/
│   │   ├── Dockerfile
│   │   └── go.mod
│   ├── identity-svc/              # Go
│   │   ├── cmd/main.go
│   │   ├── internal/
│   │   │   ├── handler/          # gRPC handlers
│   │   │   ├── service/          # business logic
│   │   │   ├── repository/       # PostgreSQL queries
│   │   │   └── model/            # domain models
│   │   ├── migrations/
│   │   ├── Dockerfile
│   │   └── go.mod
│   ├── ingestion-svc/             # Python
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── core/             # config, exceptions, middleware
│   │   │   ├── parsers/          # PDF, DOCX, HTML, TXT parsers
│   │   │   ├── chunking/         # recursive splitter, semantic splitter
│   │   │   ├── embedding/        # Ollama embed client
│   │   │   ├── graph/            # entity extraction, Neo4j writer
│   │   │   ├── saga/             # saga orchestrator
│   │   │   ├── repositories/     # PostgreSQL, Qdrant, Neo4j repos
│   │   │   ├── schemas/          # Pydantic models
│   │   │   └── services/         # business logic
│   │   ├── migrations/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── retrieval-svc/             # Python (similar structure)
│   ├── inference-svc/             # Python (similar structure)
│   ├── evaluation-svc/            # Python (similar structure)
│   ├── governance-svc/            # Go (similar to identity-svc)
│   ├── finops-svc/                # Go (similar to identity-svc)
│   ├── observability-svc/         # Go (similar to identity-svc)
│   └── frontend/                  # TypeScript/Next.js
│       ├── src/
│       │   ├── app/               # Next.js app router
│       │   ├── components/
│       │   ├── hooks/
│       │   ├── services/          # API client
│       │   └── utils/
│       ├── Dockerfile
│       └── package.json
├── infra/
│   ├── kind/
│   │   └── kind-config.yaml
│   ├── istio/
│   │   ├── gateway.yaml
│   │   ├── virtual-services/
│   │   ├── destination-rules/
│   │   ├── peer-authentication.yaml
│   │   └── authorization-policies/
│   ├── k8s/
│   │   ├── namespaces.yaml
│   │   ├── data-stores/           # PostgreSQL, Qdrant, Neo4j, Redis, Kafka manifests
│   │   ├── services/              # Deployment + Service + HPA per service
│   │   └── network-policies/
│   └── docker-compose.yml         # Dev fallback
├── scripts/
│   ├── cluster-up.sh
│   ├── cluster-down.sh
│   ├── seed-data.sh
│   └── run-eval.sh
├── docs/
│   ├── architecture/
│   │   ├── C4-context.md
│   │   ├── C4-container.md
│   │   ├── C4-component.md
│   │   └── ADRs/
│   ├── design-areas/              # One doc per design area (interview prep)
│   │   ├── 01-system-boundary.md
│   │   ├── ...
│   │   └── 67-socio-technical.md
│   ├── runbooks/
│   │   ├── DR_RUNBOOK.md
│   │   └── INCIDENT_RESPONSE.md
│   └── API.md
├── Makefile
├── .env.template
├── .gitignore
└── README.md
```

---

## 11. Success Criteria

You will know this project is interview-ready when:

1. **All 10 services** run in Kind with Istio, communicating via gRPC + Kafka
2. **Upload a PDF** → it gets parsed, chunked, embedded, indexed in Qdrant + Neo4j
3. **Ask a question** → get an answer with citations from the uploaded document
4. **Multi-tenant** → two tenants see only their own documents
5. **Circuit breaker** → stop Ollama → system degrades gracefully, no cascade
6. **Canary deploy** → deploy new Inference version with 10% traffic split via Istio
7. **Evaluation** → run eval suite, see precision/recall/faithfulness metrics
8. **HITL** → low-confidence answer appears in review queue, reviewer approves it
9. **FinOps** → see token cost per tenant in dashboard
10. **Observability** → trace a single request across all services via Jaeger correlation ID
11. **Feature flag** → toggle a feature for one tenant without deployment
12. **Chaos test** → inject fault via Istio, verify system recovers

---

*End of specification.*
