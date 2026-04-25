# RAG Data Layers And Retrieval

This document captures the main data and retrieval layers in a RAG system:

- chunking
- token handling
- embeddings
- vector databases
- pre-retrieval
- post-retrieval
- cache databases
- historical databases
- graph databases

The goal is not only to define them, but to show how they fit together in a production-quality enterprise RAG system.

## 1. Chunking

Chunking is how raw content is broken into units that can be embedded, indexed, retrieved, cited, and packed into prompts.

### Core topics

- fixed-size chunking
- overlap strategy
- semantic chunking
- hierarchical chunking
- adaptive chunking by content type
- metadata carried with each chunk
- citation-safe chunk boundaries
- chunk quality evaluation

### Why it matters

Chunking affects:

- retrieval recall
- retrieval precision
- prompt context efficiency
- citation quality
- answer faithfulness
- embedding cost

### Common questions

- how big should chunks be?
- how much overlap is enough?
- should tables, code, and prose chunk differently?
- when should chunks be merged or split later?

## 2. Token Handling

Token behavior matters because models, rerankers, and embedders all operate under token limits and token-based cost.

### Core topics

- token counting
- tokenizer mismatch
- context window budgeting
- truncation policy
- token-aware prompt assembly
- token-aware chunk selection
- token cost monitoring

### Why it matters

A system can retrieve the right information and still fail because:

- the prompt is too large
- the wrong chunks were kept
- truncation removed the important evidence
- token cost became too high

## 3. Embeddings

Embeddings convert content and queries into vector representations for similarity search.

### Core topics

- embedding model selection
- embedding dimensionality
- normalization
- dense vs sparse embeddings
- multilingual embeddings
- embedding versioning
- re-embedding strategy
- embedding drift
- embedding latency and cost

### Why it matters

Embedding quality strongly shapes:

- search quality
- multilingual performance
- cost
- reindexing complexity
- long-term maintainability

### Common operational concerns

- when to re-embed all documents
- how to handle mixed-version embeddings
- how to compare old and new embedding models safely

## 4. Vector Database

The vector database stores embeddings and supports similarity search over them.

### Core topics

- index design
- similarity metrics
- ANN search
- top-k retrieval
- metadata filtering
- tenant isolation
- hybrid retrieval support
- index rebuild strategy
- observability and maintenance

### Why it matters

The vector DB is often where retrieval quality and performance trade off directly.

Poor vector DB design leads to:

- low recall
- noisy results
- slow search
- expensive filtering
- tenant leakage risk

## 5. Pre-Retrieval

Pre-retrieval is everything done before actual search to improve retrieval quality and constrain the search space.

### Core topics

- query rewriting
- query expansion
- intent detection
- query classification
- tenant and policy filtering
- source selection
- time-range filtering
- trust-tier filtering
- context budget planning

### Why it matters

Many retrieval failures are really pre-retrieval failures:

- wrong query formulation
- wrong source set
- wrong tenant scope
- unnecessary search over irrelevant data

### Example

Instead of searching every source for:

`vacation policy`

the system may first decide:

- tenant = `acme`
- source class = HR docs only
- latest policy versions only
- high-trust internal content only

That is pre-retrieval value.

## 6. Post-Retrieval

Post-retrieval is what happens after results come back and before generation consumes them.

### Core topics

- reranking
- deduplication
- chunk merging
- score thresholding
- citation selection
- context packing
- conflict resolution across sources
- retrieval quality scoring
- groundedness checks before generation

### Why it matters

Retrieval output is often too noisy or too large to use directly.

Post-retrieval decides:

- what evidence survives
- what evidence is suppressed
- how evidence is ordered
- how the final prompt is packed

This is one of the most important quality layers in a RAG system.

## 7. Cache Database

Caching reduces repeated work and latency across the retrieval and generation pipeline.

### Core topics

- result cache
- embedding cache
- prompt cache
- retrieval cache
- cache key design
- TTL strategy
- tenant-safe cache keys
- invalidation
- cache hit/miss monitoring

### Why it matters

Caching can improve:

- latency
- cost
- system throughput

But weak cache design can create:

- stale answers
- cross-tenant leakage
- invalid cached retrieval context
- misleading “fast but wrong” behavior

## 8. Historical Database

A historical database stores prior states, versions, events, or audit trails.

### Core topics

- audit history
- versioned documents
- temporal queries
- replay history
- event history
- immutable logs
- lineage tracking
- rollback support
- retention policy

### Why it matters

Historical storage helps with:

- compliance
- debugging
- replay workflows
- lineage explanation
- user trust

RAG systems often need to explain not only what answer was given, but:

- which version of the source was used
- what changed later
- what event led to this state

## 9. Graph Database

A graph database represents entities and relationships explicitly, enabling graph traversal and multi-hop reasoning support.

### Core topics

- entity extraction
- relationship extraction
- graph schema design
- graph traversal
- path-based retrieval
- graph + vector hybrid retrieval
- graph freshness
- tenant isolation in graph data
- graph explainability

### Why it matters

Graph retrieval is useful when questions depend on:

- entity relationships
- dependency chains
- multi-hop connections
- explainable traversal paths

This matters in enterprise settings like:

- organizational structures
- ownership graphs
- system topology
- document-to-entity linking

## 10. How These Layers Work Together

A common production pipeline looks like:

1. ingest content
2. chunk content
3. count tokens and validate chunk shape
4. generate embeddings
5. store embeddings in vector DB
6. optionally extract entities and edges into graph DB
7. at query time, run pre-retrieval logic
8. search vector DB and optionally graph DB
9. apply post-retrieval logic
10. optionally use cache before or after retrieval
11. assemble prompt and generate answer
12. write audit or historical records

That is the layered view of enterprise RAG.

## 11. Important Combined Scenario Groups

- chunking -> embedding -> vector indexing
- query rewrite -> pre-retrieval filtering -> vector search
- vector retrieval -> graph expansion -> reranking
- reranking -> context packing -> answer generation
- cache hit -> skip retrieval path
- cache miss -> retrieval path -> cache fill
- historical lookup -> replay or audit explanation
- graph traversal + vector similarity for multi-hop questions

## 12. Common Failure Patterns

- chunks too small or too large
- token budget ignored until generation time
- embeddings drift after model change
- vector DB filters applied incorrectly
- pre-retrieval over-constrains and misses relevant data
- reranker suppresses needed evidence
- cache serves stale or cross-tenant data
- historical store lacks version fidelity
- graph is stale or only partially built

## 13. Senior-Level Questions

A strong engineer asks:

- where is retrieval quality actually being won or lost?
- what layer is responsible for this failure?
- can the system explain why this chunk was retrieved?
- can we reproduce the answer using stored history and versioned data?
- where are cost and latency accumulating?
- how do vector, graph, cache, and history layers interact under failure?

## 14. Best Next Topics

Natural follow-up topics are:

- chunking scenarios and evaluation
- embedding strategy and migration
- hybrid retrieval design
- reranking and context packing
- graph retrieval patterns
- retrieval observability and scoring

---

## 15. How These Layers Map To DocuMind Today

### Already covered

| Layer | Where in repo | Drill |
| --- | --- | --- |
| Chunking | `services/ingestion-svc/app/chunking/` | GAP — no chunk-quality drill |
| Embeddings | `services/retrieval-svc/app/services/embedder_client.py` (Ollama, `nomic-embed-text`, 768-d) | none yet |
| Vector DB | Qdrant `chunks` collection, 768-d cosine | `drill_retrieval_tenant_isolation` |
| Tenant filter (vector) | `vector_searcher.py` `must_filter` on `tenant_id` | `drill_retrieval_tenant_isolation` (identical-vector test) |
| Hybrid retrieval | `hybrid_retriever.py` (vector + graph + RRF reranker) | `drill_retrieval_degraded_envelope` |
| Reranker | `services/retrieval-svc/app/services/reranker.py` (RRF) | exercised by degraded-envelope drill |
| Result cache | `Cache.set_json` / `get_json` (Redis-backed via `documind_core.cache`) | covered indirectly — cache-skip on degraded |
| Cache key tenant scoping | `Cache.tenant_key(tenant_id, "retr", h)` | proven cross-tenant safe |
| Audit history (immutable + replay) | `governance.audit_log` per-tenant hash chain | `drill_audit_verifier`, `drill_audit_seal` |
| Graph DB | Neo4j via `services/retrieval-svc/app/services/graph_searcher.py` | none yet |

### Gaps surfaced (good loop candidates)

| Layer | Gap | Severity |
| --- | --- | --- |
| Chunk quality eval | No drill for size / overlap / boundary respect. | medium |
| Embedding versioning | Model name/dim recorded in code; no per-chunk stamp. | medium |
| Embedding cache | Not implemented — every retrieval re-embeds the query. | **high** (perf + cost) |
| Sparse / hybrid lexical (BM25) | Vector + graph only. | low (architectural choice) |
| Pre-retrieval (query rewrite, intent) | Not implemented. | medium |
| Cross-encoder reranker | RRF only. | low |
| Cache-hit / miss Prometheus series | Logs exist; no metric. | medium |
| Embedding drift detection | None. | medium |
| Graph freshness signal | No "stale graph" indicator. | low |
| Time-range / trust-tier filters | Not in `RetrieveRequest`. | low |

### Drills that exist for the analogue

| Scenario | Existing drill |
| --- | --- |
| Tenant isolation in vector search | `drill_retrieval_tenant_isolation` |
| Partial-results envelope (cache-skip on degraded) | `drill_retrieval_degraded_envelope` |
| Audit chain integrity (historical layer) | `drill_audit_verifier`, `drill_audit_seal` |
| Cross-tenant audit isolation | `drill_audit_actor_type` |

### Highest-priority additions

1. **Embedding cache** — `Cache.tenant_key(tenant_id, "embed", sha(q))`.
   Cuts Ollama calls to near-zero on hot queries. Drill: second
   identical query has 0 Ollama hits.
2. **Cache-hit / miss metric** — `documind_retrieval_cache_total
   {outcome}` (hit / miss / skip-degraded / poison-skip).
3. **Embedding-version stamp on chunks** — record
   `embedding_model` + `embedding_dim` + `embedding_version` in
   the Qdrant payload so drift is detectable and a future re-embed
   job can target only stale chunks.
4. **Chunk-quality drill** — size distribution, no chunks straddle
   policy boundaries, overlap is the expected percentage.
5. **Query rewrite hook** — `pre_retrieve` step so the agent path
   can rewrite an action-shaped query into a tool call instead of
   a retrieval.
