# Repo gRPC And Microservice Architecture

This note explains how gRPC and microservice thinking fit this repo specifically.

The key point is:

- the repo is clearly microservice-oriented
- the repo’s docs and contracts assume a gRPC-friendly internal architecture
- but the currently visible live path in code still leans heavily on HTTP and reverse-proxy style routing

That distinction matters.

## 1. Current Microservice Shape

The repo is decomposed into clear services:

- `api-gateway`
- `identity-svc`
- `ingestion-svc`
- `retrieval-svc`
- `inference-svc`
- `evaluation-svc`
- `governance-svc`
- `finops-svc`
- `observability-svc`
- `frontend`

This is already a real microservice architecture shape, not a toy monolith.

## 2. What The Repo Uses Microservices For

This decomposition is useful here because different services own different concerns:

- gateway and trust boundary
- identity and auth
- document ingestion
- retrieval
- inference
- evaluation
- governance and audit
- cost and FinOps
- observability

That split is coherent for a system with:

- RAG
- MCP tool execution
- governance-sensitive workflows
- separate operational concerns

## 3. gRPC In This Repo

The repo strongly signals gRPC intent through:

- `proto/`
- architecture docs
- service decomposition docs

Relevant paths:

- [proto](/mnt/deepa/rag/proto)
- [docs/architecture/C4-container.md](/mnt/deepa/rag/docs/architecture/C4-container.md)
- [docs/design-areas/table/04-contracts-retrieval-cache.md](/mnt/deepa/rag/docs/design-areas/table/04-contracts-retrieval-cache.md)

However, the currently visible edge flow in running code is centered on:

- [services/api-gateway/cmd/main.go](/mnt/deepa/rag/services/api-gateway/cmd/main.go)
- [services/api-gateway/internal/proxy/proxy.go](/mnt/deepa/rag/services/api-gateway/internal/proxy/proxy.go)

That means the honest reading is:

- gRPC is part of the intended contract architecture
- HTTP proxying is still heavily present in the currently visible implementation path

## 4. Repo-Specific Architecture Pattern

The practical shape is:

```text
Frontend
  -> API Gateway
  -> internal services
      -> retrieval
      -> inference
      -> governance
      -> identity
      -> ingestion
```

Where relevant, services also communicate with:

- PostgreSQL
- Qdrant
- Neo4j
- Redis
- Kafka
- Ollama
- MCP servers

## 5. Where gRPC Helps This Repo

If the repo fully leans into internal gRPC, the best-fit areas are:

- service-to-service contracts between gateway and internal services
- identity and governance contracts
- retrieval and inference request contracts
- evaluation service APIs

Why:

- strong typed contracts
- generated clients
- easier version control for internal APIs
- lower ambiguity than ad hoc JSON contracts

## 6. Where HTTP Still Makes Sense

HTTP still makes sense for:

- external browser-facing APIs
- gateway-facing REST-like routes
- compatibility with frontend flows
- simple health and admin endpoints
- MCP servers, which are intentionally HTTP tool servers in this repo

That means this repo does not need to be “all gRPC everywhere.”

## 7. Monitoring gRPC And Microservices In This Repo

Even if internal contracts move more strongly to gRPC, the main observability requirements stay the same.

### Service monitoring

- request count by service
- p50, p95, p99 latency by route or method
- error rate by service and endpoint
- saturation and backlog
- dependency error rate

### Cross-service monitoring

- trace continuity across gateway -> retrieval -> inference -> MCP
- tenant and correlation propagation
- error mapping consistency
- replay and draft visibility across services

### gRPC-specific monitoring

If internal gRPC becomes more prominent, add:

- per-RPC method latency
- status-code distribution
- deadline exceeded rate
- retry rate
- protobuf compatibility checks in CI

## 8. Main Risks In This Repo’s gRPC/Microservice Story

### Risk 1: architecture drift

Docs can imply a cleaner internal gRPC shape than the current code fully enforces.

### Risk 2: contract drift

If `proto/` exists but runtime paths are not truly generated and enforced from those contracts, drift becomes possible.

### Risk 3: observability gaps

Multi-service systems fail operationally when trace continuity is weak.

### Risk 4: over-segmentation

Too many services without strong ownership and monitoring create operational tax without enough value.

## 9. Best Next Steps For This Repo

If the repo wants to strengthen this area, the best next steps are:

1. clarify current-state vs target-state gRPC usage
2. make `proto/` the explicit source of truth where gRPC is intended
3. add contract-test discipline around internal APIs
4. ensure tracing and tenant propagation across all service hops
5. keep browser-facing and MCP-facing HTTP paths explicit and honest

## 10. Bottom Line

This repo already has a strong microservice architecture direction.

Its gRPC story is best described as:

- architecturally intended
- partly scaffolded
- not yet something that should be oversold as fully realized across every internal path

That is still a strong place to be, as long as the docs stay honest.
