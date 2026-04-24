# DocuMind — Scenario Execution Specs

Executable specs per topic group. Each phase doc has scenarios with concrete
verification commands (curl / kubectl / psql / pytest) so anyone can run them
and see green/red without asking the author.

## Phase index

| Phase | Topic group | Doc | Status |
| --- | --- | --- | --- |
| 1 | Edge · Traffic · Security (API Gateway · CDN · LB · mTLS · Istio) | [phase-01-edge-traffic-security.md](phase-01-edge-traffic-security.md) | ✅ Full — 47 scenarios with verification commands |
| 2a | Microservices · Service catalog + APIs | [phase-02-microservices.md](phase-02-microservices.md) | ✅ Full — service table, API list, anti-patterns |
| 2b | Kafka · Event architecture (topic catalog + schema + DLQ) | [phase-02-kafka-event-architecture.md](phase-02-kafka-event-architecture.md) | ✅ Full — 17 topics + envelope + partition strategy |
| 3 | Circuit Breakers (generic + 5 specialized + CCB + fallback matrix) | [phase-03-circuit-breakers.md](phase-03-circuit-breakers.md) | ✅ Full — layered design, config table, 8 chaos drills |
| 4 | RAG Core (chunking · embeddings · retrieval · inference · cache · eval) | [phase-04-rag-core.md](phase-04-rag-core.md) | ✅ Full — 3 flow diagrams, quality metrics, pitfalls |
| 5 | Databases (PG · Qdrant · Neo4j · Redis · Kafka · MinIO + failure matrix) | [phase-05-databases.md](phase-05-databases.md) | ✅ Full — per-store scenarios + fallbacks |
| 6 | MCP + Agentic (13 agent + 14 MCP scenarios + trust boundary) | [phase-06-mcp-agentic.md](phase-06-mcp-agentic.md) | ✅ Full — **zero code yet, biggest gap** |
| 7 | Observability · Audit · SLO · Chaos | [phase-07-observability.md](phase-07-observability.md) | ✅ Full — metrics + SLO catalog + 9 chaos drills |
| 8 | Governance · FinOps · Evaluation | [phase-08-governance-finops-eval.md](phase-08-governance-finops-eval.md) | Stub — exit criteria only |
| 9 | PII Protection (detect · tag · redact · audit) | [phase-09-pii-protection.md](phase-09-pii-protection.md) | ✅ Full — 8 scenarios · flow diagram · CEL policy · 6 test cases |
| 10 | LDAP / SSO (OIDC · SAML · SCIM · JWT claims) | [phase-10-ldap-sso.md](phase-10-ldap-sso.md) | ✅ Full — sequence diagram · JWT schema · 10 security scenarios |
| 11 | RBAC + ABAC (role + attribute + policy engine) | [phase-11-rbac-abac.md](phase-11-rbac-abac.md) | ✅ Full — 8 RBAC + 10 ABAC scenarios · combined flow · failure matrix |
| 12 | Guardrails + Secure AI (5 layers · attack/defense matrix) | [phase-12-guardrails-secure-ai.md](phase-12-guardrails-secure-ai.md) | ✅ Full — input/retrieval/prompt/output/action guards · 10 attack vectors |
| 15 | **Master Blueprint + Golden Vertical Slice** | [phase-15-master-blueprint.md](phase-15-master-blueprint.md) | ✅ Full — master flow diagram · 10-step demo script · failure drills · current execution state |
| 21 | Embeddings (types · models · versioning · benchmarking) | [phase-21-embeddings.md](phase-21-embeddings.md) | ✅ Full — BGE-m3 default · critical checks · failure matrix |
| 20 | Chunking (types + config + TDD/BDD/MDD/output-first + checklist) | [phase-20-chunking.md](phase-20-chunking.md) | ✅ Full — hierarchical default · engineering-methodology layer · validation checklist |
| 22 | Tokens (budget + estimation + optimization + metrics) | [phase-22-tokens.md](phase-22-tokens.md) | ✅ Full — allocation % · failure matrix · 9 optimization strategies |
| 23 | Capacity Planning (QPS + cost + storage + load tests) | [phase-23-capacity.md](phase-23-capacity.md) | ✅ Full — component targets · token-driven capacity · load-test contracts |
| 24 | Pre/Post Retrieval (query rewrite · rerank · dedup · compress) | [phase-24-pre-post-retrieval.md](phase-24-pre-post-retrieval.md) | ✅ Full — combined flow diagram · failure matrices for both sides |
| 25 | Evaluation (LLM · RAG · MCP · Agent · A2A) | [phase-25-evaluation.md](phase-25-evaluation.md) | ✅ Full — 5 eval layers · TDD + BDD · golden dataset exit criterion |

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

## Execution order — what to build next

1. **Day 1.5** — start the Python services as processes; verify POST `/documents` → saga → POST `/ask` → cited answer. Closes the end-to-end claim.
2. **Phase 3 §11 exit criteria** — implement `@with_resilience` decorator; wrap every external call site. Closes the "CB not integrated" gap.
3. **Phase 7 §7 chaos drills** — run 9 drills against the running stack; capture Grafana screenshots + trace links.
4. **Phase 6 §8 exit criteria** — build `mcp/client.py` + one `mcp/server_*.py` end-to-end. Closes the "MCP aspirational" gap.
5. **Phase 4 §6 exit criteria** — commit the golden dataset + wire `make eval`. Closes the "no eval pipeline" gap.

Everything else depends on these five.
