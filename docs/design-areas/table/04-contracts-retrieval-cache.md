# Areas 30–42 · Contracts, Retrieval/Knowledge Lifecycle, Cache

## Area 30 · API Contract Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | FastAPI auto-OpenAPI; `proto/*/v1/*.proto`; `libs/py/documind_core/schemas.py` |
| **Components** | REST (external) · gRPC (internal) · Protobuf · OpenAPI 3.1 · versioned URLs |
| **Technical details** | REST for browsers/BFF; gRPC for service-to-service (HTTP/2, typed, codegen). `/api/v1/`, `/api/v2/` for breaking changes. |
| **Implementation** | FastAPI auto-generates OpenAPI from Pydantic models. Proto files are the source of truth for internal RPCs; codegen produces Go + Python stubs. |
| **Tools & frameworks** | FastAPI + Pydantic · gRPC · buf.build (proto linting) · Pact (contract tests) · Schemathesis (fuzz API) |
| **How to implement** | 1. Design contract first (OpenAPI/proto) · 2. Generate stubs · 3. Contract tests in CI · 4. Version on breaking change · 5. Deprecation window ≥ 2 versions. |
| **Real-world example** | Adding `display_name` field → minor (additive). Removing `email` → major version bump. |
| **Pros** | Typed clients · Catches breaks in CI · Clear semantics |
| **Cons** | Schema-first discipline · Codegen pipeline · Proto learning curve |
| **Limitations** | gRPC via browser needs grpc-web or gateway transcoding · OpenAPI examples drift |
| **Recommendations** | Consumer-driven contract tests (Pact) · `buf breaking` in CI · Semantic versioning strict |
| **Challenges** | Cross-team schema review · Deprecation discipline · Backwards-compat shims |
| **Edge cases + solutions** | Two clients on different versions → keep both paths live for N releases · Breaking change → new URL (`/api/v2/`) or new proto package |
| **Alternatives** | GraphQL (flexible, harder to cache) · JSON-RPC · HTTP-only with JSON Schema |

---

## Area 31 · Event Contract Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `schemas/events/*.json` (CloudEvents JSON Schema), `kafka_client.EventProducer` enforces envelope |
| **Components** | CloudEvents 1.0 envelope · JSON Schema per event type · Version in `type` (`document.indexed.v1`) · Schema registry |
| **Technical details** | Every event is self-describing with id, source, type, specversion, time, tenantid, correlationid, data. |
| **Implementation** | Producer validates event payload against schema before publishing. Consumer revalidates. Version bump = new type string; consumers migrate. |
| **Tools & frameworks** | CloudEvents spec · JSON Schema draft-07 · Confluent Schema Registry (Avro option) · `jsonschema` (Python) · `buf` for Proto events |
| **How to implement** | 1. Write JSON Schemas · 2. Producer validate · 3. Consumer validate · 4. Deprecation rule: additive only within version · 5. DLQ for schema-fail messages. |
| **Real-world example** | Adding `processing_time_ms` to `document.indexed.v1` → fine (optional). Removing `chunks_count` → publish `v2`. |
| **Pros** | Contract safety · Multi-consumer support · Replay-compatible |
| **Cons** | Schema-file sprawl · Discipline required · Registry is an extra moving part |
| **Limitations** | JSON Schema expressiveness limited for complex invariants · Avro is more compact but pays dev UX |
| **Recommendations** | One schema per type · Semantic version in type · Producer = enforcer |
| **Challenges** | Schema evolution across many consumers · Legacy consumers still on v1 · Backward-compat definition |
| **Edge cases + solutions** | v1 producer + v2 consumer → consumer handles both · v2 producer + v1 consumer → v1 consumer ignores unknown fields |
| **Alternatives** | Avro + Confluent Registry · Protobuf events (binary) · XML Schema (legacy) · flat JSON, no schema (chaos) |

---

## Area 32 · Prompt Contract Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/inference-svc/app/services/prompt_builder.py`, `governance.prompts` table |
| **Components** | Prompt template · Name + version · Variables · Model + temperature + max_tokens · Status (draft/active/deprecated) · Approval workflow |
| **Technical details** | Prompts ARE code. Every LLM response records `prompt_version`. Two versions can be active with traffic split. |
| **Implementation** | `PromptTemplate` dataclass with `name`, `version`, `system`, `user_template`. Registry keyed `"rag_answer_v1"`. Real prod fetches from DB at startup + polls. |
| **Tools & frameworks** | LangSmith · PromptLayer · Humanloop · Braintrust · custom (DocuMind) |
| **How to implement** | 1. Templates in DB · 2. Version on each change · 3. Governance approval for active status · 4. Record prompt_version in response · 5. A/B via traffic weight. |
| **Real-world example** | `rag_answer_v3` bumps temp 0.1→0.2 → staged rollout 10%→50%→100% over a week · regression gate watches faithfulness. |
| **Pros** | Traceable regressions · A/B-testable · Audit-friendly · Rollback by flipping status |
| **Cons** | Prompt engineering ≠ software engineering discipline for many teams · Sprawl |
| **Limitations** | No formal prompt linting · Embedding-model change invalidates prompts for RAG · Localization hard |
| **Recommendations** | 1:1 unit tests per prompt (golden outputs) · Regression suite in CI · Deprecation window for old versions |
| **Challenges** | Model-specific prompts · Multi-step prompt composition · Prompt injection attacks |
| **Edge cases + solutions** | Prompt drift (LLM output shifts) → regression gate catches · Jailbreak attempts → input sanitization + output guardrails |
| **Alternatives** | In-code string constants (no versioning, don't) · Jinja2 templates (loose) · LangChain PromptTemplate |

---

## Area 33 · Output Contract Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/inference-svc/app/services/guardrails.py`, `CognitiveCircuitBreaker` signals |
| **Components** | Required fields (answer, citations, confidence) · Forbidden patterns (PII, toxic) · Citation validity · Confidence score · Length check |
| **Technical details** | Every response passes post-generation guardrails AND intrinsic CCB during generation. Failures routed to HITL. |
| **Implementation** | `GuardrailChecker.check(answer, citation_map, scores)` returns `GuardrailResult` with violations + confidence. CCB runs during streaming. |
| **Tools & frameworks** | Guardrails.ai · NeMo Guardrails · Rebuff (prompt injection) · Presidio (PII) · custom (DocuMind) |
| **How to implement** | 1. Schema check · 2. Citation cross-reference · 3. PII regex + NER · 4. Confidence heuristic · 5. Length bounds · 6. Route failures to HITL. |
| **Real-world example** | Model invents `[Source: madeup.pdf, Page 999]` → citation-validity check fails · response flagged · routed to HITL queue · user sees safe fallback. |
| **Pros** | Safety net · Hallucination defense · Policy enforcement |
| **Cons** | False positives block valid answers · Calibration · Latency overhead |
| **Limitations** | Regex PII is shallow; ML-based detector better · Citation check relies on exact label format |
| **Recommendations** | Log every violation · Combine CCB (during) + Guardrails (after) · Escalate, don't silently drop |
| **Challenges** | Calibrating strictness · Localized content (PII regex is English-centric) |
| **Edge cases + solutions** | Valid answer happens to match PII regex → NER verify before block · Cited text paraphrased → fuzzy citation match |
| **Alternatives** | Guardrails.ai · NeMo Guardrails · LLM-as-judge (expensive) · Simple regex filters |

---

## Area 34 · Retrieval Schema

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/retrieval-svc/app/schemas/__init__.py`, `proto/retrieval/v1/retrieval.proto` |
| **Components** | `RetrievedChunk` with chunk_id, document_id, text, score, source, page_number, metadata |
| **Technical details** | Normalized across all backends: vector, graph, metadata all return the same shape. Reranker/fusion operate on this contract. |
| **Implementation** | Pydantic model + Proto message. `source` label tells fusion which backend found it; `score` normalized 0-1. |
| **Tools & frameworks** | Pydantic · Protobuf |
| **How to implement** | 1. One dataclass, used everywhere · 2. Normalize scores (different backends have different scales) · 3. Preserve metadata for citations. |
| **Real-world example** | Qdrant returns cosine score 0.87 · Neo4j returns mention-count 3 (normalized to 1.0) · fused by RRF into unified rank list. |
| **Pros** | Reranker/LLM consumer stays backend-agnostic · Easy to add a 3rd backend |
| **Cons** | Score normalization is tricky · Metadata bloat |
| **Limitations** | Cannot preserve per-backend debug info without metadata dict · Scores aren't directly comparable |
| **Recommendations** | Normalize to 0-1 at the source · Keep raw score in metadata · Use RRF rather than raw-score fusion |
| **Challenges** | New backends with incompatible scoring semantics · Very large metadata inflating responses |
| **Edge cases + solutions** | Backend returns negative scores (e.g. distance) → invert at source · Duplicate chunk_id from two backends → dedupe by chunk_id, highest score wins |
| **Alternatives** | Per-backend schemas + adapter pattern · LangChain Document shape · HayStack Document |

---

## Area 35 · Knowledge Lifecycle

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `document_repo.py` state machine + `ingestion/migrations/001_initial.sql` |
| **Components** | States: UPLOADED → PARSING → CHUNKED → EMBEDDED → INDEXED → ACTIVE · STALE · RE-INGEST · ARCHIVED · DELETED |
| **Technical details** | Lifecycle tracked per document. Transitions audited. Stale detection via content hash. |
| **Implementation** | State transitions in repo. ARCHIVED keeps metadata but removes from search. DELETED cascades across all stores via saga. |
| **Tools & frameworks** | Postgres state machine · cron for stale detection · content hash (SHA-256) |
| **How to implement** | 1. State transitions explicit · 2. Hash on ingest · 3. Cron checks source → stale if hash changes · 4. TTL-based archive per tenant policy. |
| **Real-world example** | User re-uploads same filename · hash differs → old doc marked STALE · new doc goes through full pipeline · old vectors garbage-collected after 24h. |
| **Pros** | Predictable ops · Audit trail · Retention policy enforceable |
| **Cons** | Many states to maintain · Stale detection is probabilistic (source may be a live URL) |
| **Limitations** | Doesn't handle document-level ACLs (per-user visibility) |
| **Recommendations** | Per-tenant retention policy · Archive, don't delete immediately (legal hold) |
| **Challenges** | Source-of-truth outside your system · Large retention windows · GDPR deletion |
| **Edge cases + solutions** | Source URL dead → treat as STALE + alert · Partial re-ingest → previous version kept until new reaches ACTIVE |
| **Alternatives** | Immutable versioned docs (CRDT-ish) · Event-sourced knowledge · Full replace-every-time (simple, wasteful) |

---

## Area 36 · Source Trust Model

| Field | Content |
|---|---|
| **Status** | ❌ Designed only |
| **Class / file** | `docs/superpowers/specs/2026-04-23-documind-system-design.md` §36 |
| **Components** | Trust levels (verified/trusted/unverified/untrusted) · Score multiplier on retrieval · Governance action (auto-serve vs flag) |
| **Technical details** | Per-document trust attribute. Multiplies retrieval score. Unverified-only results flagged for HITL. |
| **Implementation (planned)** | `ingestion.documents.trust_level` column · retrieval fetches and multiplies · governance policy triggers HITL for low-trust sole source. |
| **Tools & frameworks** | Custom · W3C Verifiable Credentials for document provenance (future) |
| **How to implement** | 1. Add column + default 'unverified' · 2. Admin UI to verify · 3. Retrieval applies multiplier · 4. Governance rule for auto-flag. |
| **Real-world example** | Contract from internal repo → `verified` (1.5x boost) · uploaded by user → `unverified` (0.8x + flag if sole source). |
| **Pros** | Quality signal for retrieval · Compliance · Explainability |
| **Cons** | Verification workflow effort · User confusion ("why is my doc untrusted?") |
| **Limitations** | Trust is binary-ish even with 4 levels; real-world is continuous |
| **Recommendations** | Start with 2 levels (trusted/unverified) · Verify via checksum + allow-listed upload source |
| **Challenges** | Automating verification · Promoting documents between tiers |
| **Edge cases + solutions** | Only-source-is-untrusted → HITL · Verified doc goes stale → drops to trusted until re-verified |
| **Alternatives** | Boolean "verified" only · W3C VC (prod-grade provenance) · No trust model (current state) |

---

## Area 37 · Historical Knowledge Policy

| Field | Content |
|---|---|
| **Status** | ❌ Designed only |
| **Class / file** | `spec §37`; schema has `previous_version_id` placeholder |
| **Components** | Version chain · Temporal filter (`latest_only` / `include_historical` / `as_of_date`) · Compliance queries |
| **Technical details** | Old docs demoted, not deleted. Retrieval defaults to latest; explicit opt-in for historical. |
| **Implementation (planned)** | `documents.previous_version_id` + `valid_from`/`valid_to`. Retrieval payload filter on `valid_to IS NULL`. |
| **Tools & frameworks** | Bitemporal modeling · SCD Type 2 (slowly changing dimension) · Postgres range types |
| **How to implement** | 1. Version pointers · 2. Default query excludes superseded · 3. `as_of_date` param · 4. Compliance dashboards. |
| **Real-world example** | Legal asks "what did the policy say on Jan 15?" → `as_of_date=2024-01-15` · retrieval filters to docs valid at that date. |
| **Pros** | Legal/compliance safe · Time-travel queries · Traceable changes |
| **Cons** | Index size grows · Query complexity |
| **Limitations** | Bitemporal queries slow without careful indexing |
| **Recommendations** | Version chain explicit · Retention per tenant · Separate cold-storage for deep history |
| **Challenges** | Versioned embeddings (re-embed across versions?) · Retrieval across time |
| **Edge cases + solutions** | Query spans multiple versions → dedup by `document_id`, keep latest within window · Deep history → cold tier |
| **Alternatives** | Single-version with audit log · Event-sourced docs · Temporal tables (SQL Server / Postgres extension) |

---

## Area 38 · Index Lifecycle

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — `ensure_collection` + swap-alias pattern documented; zero-downtime rebuild job deferred |
| **Class / file** | `services/ingestion-svc/app/repositories/qdrant_repo.py::ensure_collection` |
| **Components** | Collection creation · HNSW config · Payload indexes · Quantization · Rolling rebuild (alias swap) · Health checks |
| **Technical details** | One collection shared across tenants (payload filter). Rebuild strategy: create `chunks_v2` → index in background → swap alias → drop v1. |
| **Implementation** | `ensure_collection` idempotent; creates HNSW + scalar quantization. Rebuild script (planned) orchestrates alias swap. |
| **Tools & frameworks** | Qdrant aliases · Weaviate schema mutations · Pinecone namespaces |
| **How to implement** | 1. Idempotent ensure · 2. Aliases for swap · 3. Validation queries before swap · 4. Shadow traffic for verify · 5. Atomic swap. |
| **Real-world example** | Switch embedding model: create `chunks_v2` · re-embed corpus in background · sample queries compare v1 vs v2 · swap when tolerance met · delete v1 after 7-day grace. |
| **Pros** | Zero-downtime upgrades · A/B between indexes · Rollback if bad |
| **Cons** | 2x storage during migration · Re-embed cost · Complex operator play |
| **Limitations** | Qdrant alias swap is atomic per node; cluster-wide needs leader coordination |
| **Recommendations** | Always use aliases · Validation queries in pipeline · Staged cutover (10%→50%→100%) |
| **Challenges** | Embedding drift during migration · Traffic skew during cutover · Rollback after cutover |
| **Edge cases + solutions** | Midway failure → keep v1 live, mark v2 "failed" · Validation miss → delay cutover |
| **Alternatives** | Re-embed in-place (downtime) · Dual-write during migration (complexity) |

---

## Area 39 · Embedding Lifecycle

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — `embedding_model` tracked per chunk; re-embed job deferred |
| **Class / file** | `ingestion.chunks.metadata` holds model/version fields; `EmbeddingProvider` interface |
| **Components** | `embedding_model` · `embedding_version` · `embedding_date` per chunk · Re-embed job · Drift detection · Dimensionality enforcement |
| **Technical details** | Swap model = background re-embed, dual-vectors during migration, query routes by model. |
| **Implementation (planned)** | `metadata.embedding_model = "nomic-embed-text"`. Re-embed worker batches chunks with mismatched version. Queries filter by model on query-time embedder. |
| **Tools & frameworks** | BGE-M3 · Nomic · E5 · OpenAI text-embedding-3 · Voyage · Mixedbread |
| **How to implement** | 1. Store model+version per chunk · 2. Re-embed worker · 3. Dual vectors during migration · 4. Drift canary (embed reference texts daily). |
| **Real-world example** | Move from `nomic-embed-text` (768d) → `bge-m3` (1024d) · new collection created (different dimension) · re-embed in background · queries use matching model. |
| **Pros** | Model upgrade without downtime · Drift detectable · Reproducible |
| **Cons** | 2x storage briefly · Coordination across ingestion + retrieval · Dim changes force new collection |
| **Limitations** | Query-time embedder must match the chunk's model · If embedder service swaps model mid-flight, results degrade silently (canary catches) |
| **Recommendations** | Pin embedder version in deploy · Canary reference-text cosine · Alert on embedding drift |
| **Challenges** | Dimensionality changes force collection recreate · Quality metric to compare old vs new |
| **Edge cases + solutions** | Query reaches before re-embed done → use old-vector collection · Partial re-embed crash → resume by scanning for mismatched version |
| **Alternatives** | In-place replace (downtime) · Per-tenant isolation (some stay on old) |

---

## Area 40 · Cache Architecture

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/cache.py` |
| **Components** | Query cache (5min TTL) · Embedding cache (24h) · Tenant config cache (1min) · Policy cache (30s) · Session · Rate-limit counters |
| **Technical details** | Cache-aside with stampede-prevention lock. All keys tenant-namespaced. |
| **Implementation** | `Cache.get_or_load(key, loader, ttl)` checks, locks on miss, re-checks, calls loader, stores. `tenant_key()` enforces namespace. |
| **Tools & frameworks** | Redis · Valkey · ElastiCache · Upstash · Dragonfly |
| **How to implement** | 1. Pick TTL per use case · 2. Namespaced keys · 3. Stampede lock on miss · 4. Monitor hit rate. |
| **Real-world example** | Hot query "what is our vacation policy" → 5min TTL cache hit for 95% of queries in a 5-min window. |
| **Pros** | Massive latency + cost reduction · Cheap · Horizontally scaled |
| **Cons** | Invalidation complexity · TTL tuning · Stale reads possible |
| **Limitations** | Redis OOM cliff (eviction policy matters) · Cache stampede on popular miss |
| **Recommendations** | TTL + event-driven invalidation · Cache-aside for freshness · Per-tenant size limits |
| **Challenges** | Tenant fairness · Invalidation fan-out · Cross-region replication |
| **Edge cases + solutions** | Stampede → Redis SET NX lock · Missed invalidation → TTL upper bound · Redis crash → fail-open (origin load) |
| **Alternatives** | Local in-process (fastest but per-pod) · Memcached · CDN (for static) · Apache Ignite (distributed grid) |

---

## Area 41 · Cache Consistency

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `Cache.invalidate_prefix`, Kafka `document.lifecycle` consumer for cache bust |
| **Components** | TTL expiry · Event-driven invalidation · Write-through for config · Stampede prevention |
| **Technical details** | Most caches expire by TTL. Document-change events invalidate dependent query caches. |
| **Implementation** | `Cache.invalidate_prefix("tenant:X:retr:")` on `document.reindexed` event. Config changes write to DB + Redis simultaneously. |
| **Tools & frameworks** | Kafka consumer · Redis PUBSUB (alternative) · Redis SCAN for pattern delete |
| **How to implement** | 1. TTL as upper bound · 2. Events drive explicit invalidation · 3. Write-through for config · 4. Stampede lock. |
| **Real-world example** | Doc updated → `document.reindexed` event → cache consumer SCANs `tenant:X:retr:*` and DELs · next query re-fetches. |
| **Pros** | Freshness when it matters · Graceful degradation · Predictable bounds |
| **Cons** | SCAN is O(N) · Missed events = stale · Complexity |
| **Limitations** | `SCAN` in giant keyspaces is slow · Cross-region cache coherence hard |
| **Recommendations** | Short TTL as backstop · Events as primary · Redis cluster + consistent hashing for scale |
| **Challenges** | Invalidation fan-out latency · Kafka consumer lag · Missed events |
| **Edge cases + solutions** | Bulk update → batch invalidation · Missed event → TTL saves you within N seconds |
| **Alternatives** | Write-through (simple, slower) · Write-behind (fast, risk) · No cache (correct, slow) |

---

## Area 42 · Tenant-Aware Cache

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `Cache.tenant_key`, `rate_limiter.tenant_key` |
| **Components** | Tenant-namespaced keys · Per-tenant TTL · Per-tenant size limits · Bulk invalidation on tenant suspension |
| **Technical details** | Every key is `tenant:{uuid}:...` — cross-tenant hit impossible. Premium tenants get longer TTLs. |
| **Implementation** | Static helper `tenant_key(tenant_id, *parts)` enforces the namespace. Tenant suspension fires `tenant.suspended` event → `invalidate_prefix(f"tenant:{id}:")`. |
| **Tools & frameworks** | Redis · Redis Cluster for scale · Hashtag `{tenant:id}:...` for pinning keys to one slot |
| **How to implement** | 1. Helper for key construction · 2. Forbid direct string interpolation · 3. Per-tenant config for TTL/size · 4. Bulk invalidate on lifecycle events. |
| **Real-world example** | Tenant A suspended → all A's cache keys deleted in seconds · Tenant B unaffected · premium B tenant has 15-min TTL vs free tier's 2-min. |
| **Pros** | Structural tenant isolation · Fairness · Quota enforcement |
| **Cons** | Keyspace bloat with many small tenants · Rebalancing hot tenants |
| **Limitations** | LRU eviction ignores tenant fairness; custom eviction needed for multi-tenant · Hashtag pinning can unbalance shards |
| **Recommendations** | Hashtag by tenant for locality · Per-tenant `maxmemory-policy` via Redis ACL · Monitor hit rate per tenant |
| **Challenges** | Noisy neighbor fairness · Cross-shard bulk invalidation (SCAN per node) · Large tenant = hot shard |
| **Edge cases + solutions** | Hot tenant dominates → shard them off · Free tier overflows → aggressive eviction on that prefix |
| **Alternatives** | Dedicated Redis per tenant (isolation, cost) · App-level eviction (complex) · Per-tenant prefix sets |
