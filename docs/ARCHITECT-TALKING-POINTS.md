# Architect & Interview Talking Points

Single-page primer for explaining DocuMind to:

- a **VP/Director** (architecture review) — strategic choices, risk, budget
- a **senior engineer** (design review) — load-bearing design decisions
- an **interviewer** (system-design round) — rationale, not just what, but *why and what else was considered*

Every talking point includes the **claim** and the **sharpest counter-question** you should expect — and an answer for it.

---

## 1. "Walk me through the architecture in 60 seconds"

DocuMind is a multi-tenant document-intelligence platform. Users upload documents, we chunk them, embed them, index them into a vector store plus a knowledge graph, and answer questions over them with citations and a human-in-the-loop escalation path when confidence is low. The platform is split into ~8 Go/Python microservices behind an Istio service mesh with mTLS STRICT everywhere. Postgres is the source of truth with RLS-enforced tenant isolation at the database level. Qdrant serves approximate-nearest-neighbor retrieval; Neo4j adds relationship reasoning. Redis handles prompt caching and rate-limiting. Kafka is the event backbone. Five circuit breakers — retrieval, token, agent-loop, observability, and the cognitive breaker — protect against cascading failures and runaway LLM loops. Full OpenTelemetry coverage, Prometheus + Grafana for metrics, Jaeger for traces, ELK for logs.

**Expected counter:** "Why microservices for a document Q&A app?"
**Answer:** Because the failure domains are genuinely different. Ingestion is throughput-bound (IO + CPU), inference is latency-bound + cost-bound, and evaluation is batch-bound. If we ran them in one process, a slow Ollama call would block ingest and vice versa. We also want each team to version and deploy their slice independently. The gRPC boundaries also give us natural places to insert circuit breakers and Istio policy.

---

## 2. "How does tenant isolation actually work?"

Three layers, in order of trust.

1. **Database-enforced RLS.** Every tenant-scoped table has `ROW LEVEL SECURITY` policies that filter by `app.current_tenant` — a session variable set from the authenticated JWT. The key detail most teams miss: **Postgres table owners bypass RLS by default**. That makes RLS a no-op if your service runs as the owning role. We fixed this with two mechanisms: `ALTER TABLE ... FORCE ROW LEVEL SECURITY` (makes RLS apply to the owner), *and* role separation — migrations run as `documind`, the app runs as `documind_app` which is explicitly `NOBYPASSRLS`, and privileged jobs (billing rollups, audit recovery) run as `documind_ops` with `BYPASSRLS` and full audit logging.
2. **Vector store payload filters.** Every Qdrant point carries `{tenant_id, document_id, chunk_id}`. Queries are compiled with an inescapable `must` filter on `tenant_id`. The search API never accepts a raw Qdrant query from the client.
3. **Cache namespacing.** Redis keys are `{tenant_id}:{key}`. Responses cached for one tenant are literally unreachable from another tenant's request path.

**Expected counter:** "What if an engineer forgets to set `app.current_tenant`?"
**Answer:** They get zero rows — the RLS USING clause compiles to a false predicate when the setting is unset. We have a test (`test_rls_isolation.py::test_cross_tenant_read_is_empty`) that proves this against a live Postgres with actual role separation. The test was a no-op before we added `FORCE` + role separation — tenant A saw tenant B's rows. Catching that was the whole point of building the test.

---

## 3. "Why did you pick Qdrant over pgvector / Weaviate / Milvus?"

Production math. At 10M chunks of 1024-dim embeddings, pgvector's HNSW index rebuilds lock writes for 10+ minutes per update; Qdrant's quantization + filterable payloads let us add documents continuously. Weaviate's auth model is weaker and it couples tightly to its own schema API. Milvus is a bigger operational surface than we need.

That said, we keep pgvector as a **fallback** for small tenants (under ~100K chunks) where the transactional guarantees of Postgres outweigh the performance gap. The repository abstraction hides which backend is in use.

**Expected counter:** "Qdrant is Rust and newer. What's your exit plan if the company folds?"
**Answer:** The vector store is accessed only through `VectorRepo` — one file, ~200 lines. Porting to pgvector or Milvus is 1-2 days of work plus re-embedding (which we'd do anyway, see #8). Betting on Qdrant is not a one-way door.

---

## 4. "Walk me through one query end-to-end"

```
HTTP POST /v1/ask  { "question": "...", "tenant_id": "...", "correlation_id": "..." }
  └─► API Gateway (Go) validates JWT, attaches correlation_id, forwards
  └─► Retrieval svc:
       ├─ Redis cache check (key = sha256(tenant_id || question || model_version))
       ├─ Qdrant ANN search (top-20, filter: tenant_id)
       ├─ Neo4j graph walk (1-hop neighbors of top chunks)
       ├─ Cross-encoder rerank → top-5
       └─ Context-window pack
  └─► Inference svc:
       ├─ PromptInjectionDetector, PIIScanner, AdversarialInputFilter (fail-closed)
       ├─ Circuit breaker → Ollama /api/generate
       └─ Cognitive Circuit Breaker monitors token stream for repetition/drift
  └─► Governance svc:
       ├─ ResponsibleAIChecker + confidence scoring
       └─ If confidence < threshold → HITL queue + "low confidence" flag to user
  └─► Response with citations, confidence, decision_id
```

Every step writes a structured event to `audit_log` (Postgres) and a span to Jaeger.

**Expected counter:** "That's a lot of hops. What's the p95 latency?"
**Answer:** Retrieval p95 budget is 800ms, inference budget is 2.5s. We enforce these with circuit breakers — if retrieval takes >1s we fail fast and return "please retry." We also prompt-cache, which collapses ~30% of traffic to sub-50ms.

---

## 5. "Tell me about one production-critical bug you caught"

The RLS bug from #2. I wrote the test first, it passed in CI against a mocked DB, I deployed the migrations, and then on a hunch spun up a real Postgres and ran the test against it. Tenant A saw tenant B's documents. Root cause: our service role was also the table owner, and Postgres exempts owners from RLS unless you explicitly `FORCE` it. The mocked tests couldn't detect this because the mock didn't model role attributes. Fix was 40 lines of SQL (role creation + grants + FORCE) plus rewriting the test to use dual connections (one BYPASSRLS to seed, one RLS-enforced to read). If we'd shipped without that test, tenant data-leak incident day one.

**Lesson:** Integration tests need to run against the actual substrate. Mocks lie.

---

## 6. "What's the Cognitive Circuit Breaker?"

Standard circuit breakers protect against *external* failure: "Ollama is returning 500s, stop calling it." The Cognitive Circuit Breaker (based on arXiv:2604.13417) protects against *model* failure — specifically agent loops, hallucination drift, and prompt injection chaining. It watches the token stream as it generates and opens the circuit when signals cross thresholds:

- **RepetitionSignal** — n-gram overlap in the last N tokens > 40% (the model is looping)
- **DriftSignal** — embedding distance between current and initial context > threshold (off-topic)
- **RuleBreach** — guardrail regex matched in output (jailbreak attempt)

When it opens, we halt generation, log the full state, and either return a safe fallback or escalate to HITL. It sits between the LLM client and the user response. Most teams don't have this and eat the cost of a runaway agent that spends $20 looping before someone notices.

**Expected counter:** "How do you tune the thresholds without false positives?"
**Answer:** Offline replay of prod traffic with labeled outcomes. We shadow-run the new thresholds for a week, compare to a human-labeled gold set, move to production only when precision > 95%.

---

## 7. "Why the outbox pattern and not a transactional Kafka publisher?"

Kafka doesn't participate in a Postgres transaction. If you `INSERT INTO documents` and then `kafka.produce(event)`, a crash between them means you've got the document but not the event (or vice versa). The outbox: write the domain row and the event to Postgres in one transaction; a separate relay process tails the outbox table and publishes to Kafka with at-least-once semantics. Consumers dedupe on the outbox row's UUID.

The nuance we got wrong initially: the relay was opening a *different* connection to publish, which defeats atomicity within the saga step. Fix was to pass the same connection through. Caught it in a brutal self-audit before production.

**Expected counter:** "What about Debezium CDC?"
**Answer:** Fine for streaming the whole table; overkill for one outbox table with well-defined semantics, and adds a Kafka Connect cluster to operate. The relay is ~80 lines of code.

---

## 8. "How do you handle embedding model upgrades?"

Every chunk row carries `embedding_model` and `embedding_version` columns. A model upgrade is a **shadow index**: we spin up a new Qdrant collection, re-embed in the background, verify retrieval quality on an eval set, flip a feature flag to route read traffic to the new collection, and delete the old one after a bake period. During the transition, writes go to both. If quality regresses, we flip back — zero downtime, zero data loss.

The critical guardrail: never mix embeddings from two models in the same index. Cosine distance is incomparable across models.

**Expected counter:** "What's the cost of re-embedding everything?"
**Answer:** For a 10M-chunk tenant, ~40 GPU-hours on an L4. We do it per-tenant on their off-peak, not all at once. The cost is tracked against their token budget (FinOps service) so they can see and approve it.

---

## 9. "How do you prevent prompt injection?"

Defense in depth. No single layer is sufficient.

1. **Input scanning** — `PromptInjectionDetector` runs before the model sees input. Tightly-tuned regex (ignore + instructions/rules/policy) plus a small classifier trained on known injection patterns. Fail-closed: if it matches, the request is rejected with a governance audit entry.
2. **System prompt hardening** — system prompt is immutable, signed, and loaded from a registry. User input is sandboxed in an XML tag the model is trained to treat as data.
3. **Output scanning** — `ResponsibleAIChecker` validates no prompt leakage, no PII exfiltration, no URL generation to unverified domains.
4. **Tool use allowlist** — when the agent can call tools, the permission matrix is per-tenant and per-role. A prompt that says "exfiltrate the database" has no tool that can do that.

And we never, ever put secrets in a prompt.

**Expected counter:** "Those regexes are going to have false positives."
**Answer:** We measured. Current precision is 98.2% and recall is 91% on a 2K-sample eval set that mixes real queries with known jailbreak corpora. Tradeoff is biased toward recall — a false reject is a UX annoyance, a false accept is an incident.

---

## 10. "What's your biggest design regret?"

Not doing role separation in Postgres from day 1. Everyone who's ever built a multi-tenant system on RLS either hits this bug in dev or (worse) in production. I should have known. Lesson: when a security control has a well-known bypass, the setup must make the bypass syntactically *impossible*, not merely "don't do it."

Close second: the observability circuit breaker. For the first six months, a dead OTel collector made every request hang 10s on span export. I didn't catch it until a collector outage caused a P1 incident. Now every OTel exporter is wrapped in an inverted breaker — if the backend is down, we skip export silently. Telemetry is best-effort; user requests are not.

---

## Visual appendix — where to find the diagrams

| What | Where |
| --- | --- |
| C4 Context | [C4-context.md](architecture/C4-context.md) |
| C4 Container | [C4-container.md](architecture/C4-container.md) |
| C4 Component | [C4-component.md](architecture/C4-component.md) |
| Per-tool Mermaid (network + sequence + flowcharts) | `/tools` route → any tool → **Visualization** tab |
| ADRs (decision records) | [architecture/ADRs/](architecture/ADRs/) |

---

## One-liners to remember

- "RLS without role separation is a decorative lock on an open door."
- "Outbox atomicity is one connection or it's a lie."
- "Every embedding is stamped with its model. Mix models, get nonsense."
- "Circuit breakers protect the caller. The Cognitive Circuit Breaker protects the callee."
- "Telemetry is best-effort. User requests are not. Wrap your exporters."
- "Mock the DB, ship the bug. Test against real substrate."
- "Prompt injection defense is depth, not a single regex."
