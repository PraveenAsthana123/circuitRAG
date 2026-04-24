# DocuMind — Scenario Execution Specs

Executable specs per topic group. Each phase doc has scenarios with concrete
verification commands (curl / kubectl / psql / pytest) so anyone can run
them and see green/red without asking the author.

## Phase index

| Phase | Topic group | Doc | Status |
| --- | --- | --- | --- |
| 1 | Edge, Traffic, Security — API Gateway / CDN / LB / mTLS / Istio | [phase-01-edge-traffic-security.md](phase-01-edge-traffic-security.md) | **Drafted** — verification commands included |
| 2 | Microservices — saga / outbox / CQRS / idempotency / bulkhead | [phase-02-microservices.md](phase-02-microservices.md) | Stub |
| 3 | Circuit Breakers — generic + 5 specialized + CCB | [phase-03-circuit-breakers.md](phase-03-circuit-breakers.md) | Stub |
| 4 | RAG core — chunking / embeddings / retrieval / inference / cache / eval | [phase-04-rag-core.md](phase-04-rag-core.md) | Stub |
| 5 | Databases — Postgres / Qdrant / Neo4j / Redis / Kafka / MinIO | [phase-05-databases.md](phase-05-databases.md) | Stub |
| 6 | MCP + Agentic — agent flows + tool invocation | [phase-06-mcp-agentic.md](phase-06-mcp-agentic.md) | Stub |
| 7 | Observability — logs / traces / metrics / SLOs / chaos | [phase-07-observability.md](phase-07-observability.md) | Stub |
| 8 | Governance + FinOps + Evaluation | [phase-08-governance-finops-eval.md](phase-08-governance-finops-eval.md) | Stub |

## How to read a phase doc

Every scenario follows this shape:

- **Scenario name** — one line
- **Intent** — what this proves
- **Preconditions** — what must be running
- **Verification command** — one command, copy-paste
- **Expected result** — exact output / HTTP code / test result
- **Failure test** (where applicable) — how to deliberately break it
- **Fix / Fallback** — what happens when broken

If a scenario doesn't have a verification command, it's not shipped.
