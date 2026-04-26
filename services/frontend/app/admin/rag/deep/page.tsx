'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'chunking',
    title: '1. Chunking strategy',
    status: 'shipped',
    coreConcept: 'Token-aware splitting of source documents into retrieval-sized units. Chunk size, overlap, and boundary rules drive retrieval quality more than model choice.',
    problem: 'LLM context windows are bounded; raw documents are too long. Bad chunking either fragments meaning (too small) or loses precision (too large).',
    whyThisApproach: 'Token-aware boundaries with 10-20% overlap preserve context across splits while keeping individual chunks small enough for high-precision retrieval.',
    whenToUse: ['Any RAG pipeline', 'Long-form documents (PDF, DOCX, HTML)', 'Multi-language corpora (with language-aware boundaries)'],
    whenNotToUse: ['Single-paragraph documents (no chunking needed)', 'Strict-structured data (use structured retrieval instead)', 'Tables — use specialized table-extraction'],
    input: 'Parsed text + document metadata (type, language, page boundaries)',
    process: [
      'Detect document type and language',
      'Strip boilerplate (TOC, headers, footers)',
      'Token-count source text (model-aware tokenizer)',
      'Split at natural boundaries (paragraph, sentence) within token budget',
      'Apply 10-20% overlap between adjacent chunks',
      'Attach metadata (doc_id, chunk_index, page, language)',
    ],
    output: 'List of chunks with text + metadata, ready for embedding.',
    flowchart: `flowchart LR
  d[Document parsed] --> b[Strip boilerplate]
  b --> t[Token-count]
  t --> s[Split at boundaries]
  s --> o[Apply overlap]
  o --> m[Attach metadata]
  m --> e[Send to embedder]`,
    sequence: `sequenceDiagram
  autonumber
  participant Ing as ingestion-svc
  participant Parser as Parser
  participant Chunker as Chunker
  participant Tok as Tokenizer
  participant Emb as Embedder
  Ing->>Parser: extract(document)
  Parser-->>Ing: clean text
  Ing->>Chunker: chunk(text, policy)
  Chunker->>Tok: count tokens
  Tok-->>Chunker: counts
  Chunker-->>Ing: [{text, metadata}, ...]
  Ing->>Emb: embed batch
  Emb-->>Ing: vectors`,
    alternatives: [
      { name: 'Fixed character split', tradeoff: 'Simple; ignores semantic boundaries; bad for retrieval' },
      { name: 'Sentence-only split', tradeoff: 'Clean boundaries; chunks too small for context' },
      { name: 'Recursive structural split', tradeoff: 'Respects headings; more complex; needs parser quality' },
      { name: 'Sliding window', tradeoff: 'Easy; no semantic awareness; lots of duplication' },
    ],
    challenges: ['Chunk size tradeoff', 'Boilerplate detection', 'Multi-language', 'Tables/charts not flat text', 'Overlap waste vs context preservation'],
    edgeCases: [
      { case: 'Scanned PDF — OCR noise', solution: 'OCR confidence threshold; quarantine low-confidence pages' },
      { case: 'Multi-column layout', solution: 'Layout-aware parser; chunk per column flow' },
      { case: 'Mixed language doc', solution: 'Per-section language detection + per-language chunker' },
      { case: 'Repeated headers (page 1 vs 100)', solution: 'Boilerplate stripper detects + removes' },
    ],
    failureModes: [
      { mode: 'Chunks too small — retrieval fragments meaning', detect: 'eval-svc retrieval scores low', recover: 'Increase chunk size; re-embed' },
      { mode: 'Chunks too large — precision drops', detect: 'Top-K returns too-broad context', recover: 'Decrease size; rebuild' },
      { mode: 'Boilerplate pollutes top-K', detect: 'Same chunks across many queries', recover: 'Improve stripper; re-ingest' },
    ],
    monitoring: ['Per-doc-type chunk count distribution', 'Chunk-size distribution', 'Retrieval recall@K from eval-svc'],
    testing: ['Test against benchmark dataset; validate chunk-policy regression on retrieval scores'],
    security: ['No PII in chunks without redaction', 'Tenant_id metadata on every chunk', 'Embedding model version pinned per chunk'],
    scaling: ['Parallelize per document', 'Batch embedding calls', 'Per-doc-type policy routing'],
    maturity: {
      mvp: 'Fixed-size split, no overlap',
      production: 'Token-aware with overlap; per-doc-type policy',
      enterprise: 'Layout-aware parsers; chunk version registry; A/B chunk-policy tested',
    },
    limitations: ['Heuristic, not algorithmically optimal', 'Chunk boundaries lose some context', 'Tables/figures still hard'],
    projectFit: ['ingestion-svc chunking pipeline', 'Per-tenant Qdrant collections store chunks', 'GuardrailChecker validates citation grounding (commit ada94b9)'],
    interviewLine: 'Answer quality is downstream of retrieval quality, downstream of chunking quality. Chunking is the most operationally-impactful Python layer in the RAG stack.',
  },
  {
    slug: 'hybrid-retrieval',
    title: '2. Hybrid retrieval (vector + graph + cache)',
    status: 'shipped',
    coreConcept: 'Combine semantic vector search + structured graph traversal + cache hits for retrieval that\'s both meaning-aware and constraint-aware.',
    problem: 'Pure vector search misses explicit relationships (entity → entity, doc → author). Pure graph search misses semantic similarity. Hybrid covers both shapes.',
    whyThisApproach: 'Vector for "find chunks like this query," graph for "what entities relate to this," cache for "we already answered this." Reciprocal-rank fusion blends scores.',
    whenToUse: ['Knowledge graphs over documents', 'Entity-rich corpora', 'Repeated similar queries (cache wins)'],
    whenNotToUse: ['Pure unstructured corpus (vector alone is fine)', 'No entity model defined', 'Tiny corpus (overkill)'],
    input: 'Query text + tenant_id + retrieval config',
    process: [
      'Embed query',
      'Parallel: vector search (Qdrant) + graph traversal (Neo4j) + cache lookup',
      'Each path wrapped in its own circuit breaker (ADR-008)',
      'Aggregate top-K from each',
      'Reciprocal rank fusion (RRF) for combined ranking',
      'Optional rerank with cross-encoder',
      'Mark response degraded=True if any transport CB was open',
    ],
    output: 'Ranked chunks with scores + sources + degradation flag.',
    flowchart: `flowchart LR
  q[Query] --> e[Embed]
  q --> c[Cache lookup]
  e --> v{vector_breaker}
  e --> g{graph_breaker}
  v -->|allow| qd[Qdrant ANN]
  g -->|allow| n[Neo4j traversal]
  qd --> agg[RRF fusion]
  n --> agg
  c --> agg
  agg --> r[Optional rerank]
  r --> o[Top-K + degraded flag]`,
    sequence: `sequenceDiagram
  autonumber
  participant Inf as inference-svc
  participant Ret as retrieval-svc
  participant Q as Qdrant
  participant N as Neo4j
  participant C as Cache
  Inf->>Ret: retrieve(query, tenant)
  par Vector
    Ret->>Q: ANN search
    Q-->>Ret: chunks_v
  and Graph
    Ret->>N: cypher traversal
    N-->>Ret: chunks_g
  and Cache
    Ret->>C: GET query_hash
    C-->>Ret: chunks_c (or miss)
  end
  Ret->>Ret: RRF fuse + rerank
  Ret-->>Inf: chunks + degraded flag`,
    alternatives: [
      { name: 'Vector-only', tradeoff: 'Simple; misses explicit relationships' },
      { name: 'Graph-only', tradeoff: 'Misses semantic similarity; needs entity extraction' },
      { name: 'BM25 keyword', tradeoff: 'No semantic; works for exact-match' },
      { name: 'Vector + BM25 (no graph)', tradeoff: 'Common pattern; weaker for entity-rich data' },
    ],
    challenges: [
      'Score fusion across heterogeneous engines',
      'Graph schema design + maintenance',
      'Cache invalidation on source change',
      'Per-engine breaker tuning',
    ],
    edgeCases: [
      { case: 'Vector returns broad, graph returns narrow', solution: 'RRF balances; rerank refines' },
      { case: 'Graph returns nothing for query', solution: 'Vector path fills; degraded=False' },
      { case: 'Cache stale after document update', solution: 'Invalidate on document.updated event' },
      { case: 'All transports down', solution: 'Empty chunks + degraded=True; agent answers honestly' },
    ],
    failureModes: [
      { mode: 'Single transport CB stuck open', detect: 'breaker_state per transport', recover: 'Manual probe; investigate dep' },
      { mode: 'Score fusion bias', detect: 'eval-svc retrieval scores skew', recover: 'Re-tune RRF weights' },
      { mode: 'Cache poisoning', detect: 'Cross-tenant retrieval anomaly', recover: 'Tenant key prefix; flush' },
    ],
    monitoring: [
      'Per-transport latency histograms',
      'Per-transport breaker state',
      'Hybrid retrieval recall@K',
      'Cache hit rate',
    ],
    testing: [
      'drill_retrieval_tenant_isolation (cross-tenant blocked)',
      'drill_retrieval_transport_breaker (per-transport CB)',
      'drill_retrieval_degraded_envelope (degraded flag)',
      'eval-svc /api/v1/evaluation/run with fixed dataset',
    ],
    security: [
      'Per-tenant filter on every transport',
      'No PII in cache keys or values',
      'Audit retrieval queries (volume + tenant)',
    ],
    scaling: [
      '10x: parallel transports, scale horizontally',
      '100x: per-transport replication',
      '1000x: pre-compute embeddings; tier cache',
    ],
    maturity: {
      mvp: 'Vector-only retrieval',
      production: 'Vector + cache; per-transport CB',
      enterprise: 'Vector + graph + cache + rerank; chunk/embedding version registry; A/B retrieval policy',
    },
    limitations: [
      'Score fusion is heuristic',
      'Graph schema requires upfront design',
      'Cache adds correctness story (TTL, invalidation)',
    ],
    projectFit: [
      'services/inference-svc/app/services/hybrid_retriever.py',
      'ADR-008 — transport breakers',
      'drill_retrieval_transport_breaker',
      'drill_retrieval_degraded_envelope',
    ],
    interviewLine: 'Hybrid retrieval combines semantic + structured + cached signals. The discipline is honest degradation — when one transport is down, the response declares partial coverage instead of pretending it\'s complete.',
  },
  // ---- 3. Embedding ----
  {
    slug: 'embedding',
    title: '3. Embedding model + version coupling',
    status: 'shipped',
    coreConcept: 'An embedding model converts text into a fixed-dimensional vector. The non-negotiable discipline is version coupling: every chunk + every query MUST use the same model + version, or recall collapses silently.',
    oneLiner: 'Embedding = text → vector; the version stamp is non-negotiable.',
    fiveW: {
      what: 'A model (OpenAI, BGE, e5, sentence-transformers) that maps tokens → 768/1024/1536-dim vectors. Plus a version stamp on every embedded artifact.',
      why: 'Different models live in incompatible spaces. Mixing v1 + v2 corrupts retrieval. Without a version stamp, the corpus drifts silently.',
      where: 'ingestion-svc embeds at chunk-time. retrieval-svc embeds at query-time. Both call the same Embedder (same model + version).',
      when: 'Always for any RAG system. The discipline scales with corpus size — small mistakes compound.',
      who: 'AI/ML team owns model selection. Platform owns the Embedder client + version-stamping. Eval owns recall benchmarks.',
    },
    interview30s: 'Every chunk gets stamped with embedding_model + embedding_version at ingest. Every query embedder uses the SAME values. Upgrade workflow: shadow collection → re-embed corpus → eval gate → flip alias → drop old. Without this discipline, a "small" model upgrade tanks recall by 15-20% silently. The drill rejects upserts whose embedding_version doesn\'t match the collection\'s metadata.',
    coreBuildingBlocks: [
      'Embedder class — wraps model client + version metadata',
      'Per-point payload — embedding_model, embedding_version',
      'Eval benchmark — per-model Recall@K baseline',
      'Shadow collection — for zero-downtime upgrade',
      'Drill — version mismatch rejection',
    ],
    flowchart: `flowchart LR
  T[Text chunk] --> E[Embedder model + version]
  E --> V[768-dim vector]
  V --> P[Point with payload tenant_id + emb_version]
  P --> Q[(Qdrant)]
  QQ[Query text] --> E2[SAME Embedder]
  E2 --> QV[Query vector]
  QV --> S[Search Q with filter]
  S --> R[Top-K chunks]`,
    sequence: `sequenceDiagram
  autonumber
  participant Ing as ingestion-svc
  participant E as Embedder
  participant Q as Qdrant
  Ing->>E: embed (chunks, model=v2)
  E-->>Ing: vectors
  Ing->>Q: upsert with emb_version=v2 payload
  Note over Q: collection metadata pinned to v2
  Note over Ing,Q: Drill: upsert with v1 vector to v2 collection rejected`,
    coreLayers: [
      { layer: 'Model layer', responsibility: 'OpenAI ada / BGE / e5 / sentence-transformers. Trade-off: quality vs cost vs latency.' },
      { layer: 'Embedder', responsibility: 'Stable interface; version metadata exposed; batched calls.' },
      { layer: 'Version stamp', responsibility: 'Every point + every collection metadata pinned to (model, version).' },
      { layer: 'Eval', responsibility: 'Recall@K benchmark per (model, version, dataset). Gates upgrades.' },
      { layer: 'Upgrade pipeline', responsibility: 'Shadow collection + re-embed + alias flip. Never in-place.' },
    ],
    problem: 'Models live in incompatible spaces. Without explicit version coupling, corpus drift silently destroys recall.',
    whyThisApproach: 'Stamping + drill enforcement makes drift impossible. Shadow-collection upgrade has zero downtime + provable recall preservation.',
    whenToUse: ['Any RAG system', 'Embedding-driven search', 'Multi-tenant where models may differ per tier'],
    whenNotToUse: ['Pure keyword search (no embedding)', 'Throwaway prototype'],
    input: 'Text chunk OR query + tenant_id + (model, version) from config',
    process: ['Read (model, version) from collection metadata', 'Call Embedder with batched text', 'Stamp returned vectors with payload (tenant_id, embedding_model, embedding_version)', 'Upsert OR query Qdrant'],
    output: 'Versioned vectors stored; queries embedded with matching version.',
    alternatives: [
      { name: 'Model-agnostic retrieval (BM25)', tradeoff: 'No upgrade complexity; weaker recall on semantic queries' },
      { name: 'In-place re-embed', tradeoff: 'Simpler ops; downtime + recall risk; rejected by drill' },
      { name: 'LLM-as-embedder (slow)', tradeoff: 'Best quality; expensive; slow; only for premium tier' },
    ],
    challenges: [
      'Cost of re-embedding large corpora ($$$/GPU-hours)',
      'Eval dataset must reflect production query distribution',
      'Vendor model deprecation timeline (OpenAI sunset)',
      'Cross-language embedding quality',
    ],
    edgeCases: [
      { case: 'Mid-corpus model swap', solution: 'Reject — must be all-or-nothing via shadow collection' },
      { case: 'Model returns dim != collection dim', solution: 'Reject upsert; alert ops' },
      { case: 'Re-embedding fails midway', solution: 'Resumable from checkpoint; never partial corpus' },
    ],
    failureModes: [
      { mode: 'Version drift (v1 + v2 in same collection)', detect: 'Drill rejects mismatched upsert', recover: 'Identify offending pipeline; rebuild via shadow' },
      { mode: 'Embedder service down', detect: '/health/upstreams kind=embedder', recover: 'Pause ingestion; queue chunks; resume on recovery' },
      { mode: 'Recall regresses on benchmark', detect: 'eval-svc Recall@K < tolerance', recover: 'Roll back model; investigate' },
    ],
    monitoring: ['Per-collection embedding_version', 'Embedder latency p95', 'Recall@K trend', 'Re-embed job progress'],
    testing: ['drill: upsert with mismatched embedding_version rejected', 'eval: Recall@K per (model, version)', 'integration: shadow-collection alias flip dry-run'],
    security: ['Model API keys in Vault', 'No PII in eval datasets without redaction'],
    scaling: ['Batch embedding calls (32-128 per request)', 'Re-embed: parallelize across tenants; checkpoint per 1K chunks'],
    maturity: {
      mvp: 'One model; no version field',
      production: 'Versioned + drill-enforced + shadow-collection upgrade',
      enterprise: 'Multi-model registry + per-tenant model assignment + auto-eval gates',
    },
    limitations: ['Embedder is a vendor dependency for cloud models', 'Cost grows with corpus size'],
    projectFit: ['libs/py/documind_core/embedder.py', 'mcp/tests/drill_embedding_version_coupling.py'],
    interviewLine: 'Embedding upgrade is shadow-collection + eval gate + alias flip. Never in-place. The drill rejects mismatched-version upsert at the API layer.',
  },
  // ---- 4. Pre-retrieval ----
  {
    slug: 'pre-retrieval',
    title: '4. Pre-retrieval — query expansion + rewrite',
    status: 'partial',
    coreConcept: 'Pre-retrieval transforms the user query before it hits the index: expand abbreviations, rewrite ambiguous phrasing, generate multiple hypothesis-queries (HyDE), classify intent. Improves recall at the cost of latency.',
    oneLiner: 'Pre-retrieval = make the query better; it\'s the cheapest place to lift recall.',
    fiveW: {
      what: 'A pipeline before vector search: query expansion (synonyms, abbreviations), rewrite (LLM disambiguation), HyDE (generate hypothetical answer, embed that), intent classification.',
      why: 'User queries are noisy. Expanding "PR review process" to "{pull request, code review, code-review checklist, review process}" lifts recall 10-15%.',
      where: 'retrieval-svc applies pre-retrieval before calling Embedder.',
      when: 'Recall-critical workloads; ambiguous user queries; multi-language corpora.',
      who: 'AI/ML owns rewrite + HyDE prompts. Retrieval team owns the pipeline.',
    },
    interview30s: 'Pre-retrieval is the cheapest place to lift recall. Query expansion adds synonyms + abbreviations. Rewrite uses an LLM to disambiguate vague queries. HyDE generates a hypothetical answer and embeds that — counterintuitively, hypothetical-answer-embeddings often retrieve better than query-embeddings. Intent classification routes specialized queries to specialized indices. The trade-off: latency budget. Each step adds 50-200ms; pick what fits the SLA.',
    coreBuildingBlocks: [
      'Query expander — synonym dictionary + abbreviation expansion',
      'Query rewriter — LLM call for disambiguation',
      'HyDE generator — LLM hypothetical answer → embed',
      'Intent classifier — tags query type for specialized routing',
      'Cache — common queries dedupe',
    ],
    flowchart: `flowchart LR
  Q[User query] --> EXP[Expand abbreviations + synonyms]
  EXP --> RW[LLM rewrite if ambiguous]
  RW --> HYD[HyDE: generate hypothetical answer]
  HYD --> INT[Intent classifier]
  INT --> ROUTE{Specialized index?}
  ROUTE -->|yes| SP[Specialized retrieval]
  ROUTE -->|no| GEN[General hybrid retrieval]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Ret as retrieval-svc
  participant LLM as LLM
  U->>Ret: vague query
  Ret->>Ret: expand synonyms
  Ret->>LLM: rewrite if low specificity
  LLM-->>Ret: rewritten query
  Ret->>LLM: HyDE generate hypothetical answer
  LLM-->>Ret: hypothetical
  Ret->>Ret: embed hypothetical
  Ret->>Ret: hybrid retrieval with all signals`,
    coreLayers: [
      { layer: 'Expand', responsibility: 'Synonym + abbreviation expansion. Cheap; deterministic; per-tenant dictionary.' },
      { layer: 'Rewrite', responsibility: 'LLM call to disambiguate. Skip on high-specificity queries (cost gate).' },
      { layer: 'HyDE', responsibility: 'Generate hypothetical answer; embed it; use as additional retrieval signal.' },
      { layer: 'Intent', responsibility: 'Classify query type → route to specialized index if available.' },
      { layer: 'Cache', responsibility: 'Cache pre-retrieval result by query hash; reuses across users.' },
    ],
    problem: 'Raw user queries miss recall. Synonyms unmatched, abbreviations unexpanded, ambiguous phrasing.',
    whyThisApproach: 'Cheap latency vs recall trade. HyDE specifically: LLM-generated hypothetical answer often retrieves better than query.',
    whenToUse: ['Recall-critical workloads', 'Ambiguous user queries', 'Multi-language corpora'],
    whenNotToUse: ['Sub-100ms p99 SLA', 'Cost-sensitive workloads', 'Simple keyword-match suffices'],
    input: 'User query + tenant_id + per-tenant dictionary',
    process: ['Expand synonyms + abbreviations', 'Run LLM rewrite if specificity < threshold', 'Generate HyDE if recall-critical', 'Classify intent', 'Pass enriched signals to retrieval'],
    output: 'Set of {expanded query, rewritten query, HyDE vector, intent tag} for retrieval.',
    alternatives: [
      { name: 'Skip pre-retrieval (raw query)', tradeoff: 'Fastest; lowest recall' },
      { name: 'Static synonym dictionary only', tradeoff: 'Cheap; misses rephrased queries' },
      { name: 'LLM rewrite always', tradeoff: 'Best recall; expensive; latency budget' },
    ],
    challenges: [
      'Latency budget tight (each step adds 50-200ms)',
      'LLM cost on rewrite + HyDE',
      'Intent classifier needs training data',
      'Cache poisoning — wrong rewrite cached',
    ],
    edgeCases: [
      { case: 'Rewrite changes query meaning', solution: 'Eval gate on rewrite quality; fall back to raw query if confidence low' },
      { case: 'HyDE generates fact-incorrect hypothetical', solution: 'Acceptable — used only as retrieval signal; LLM grounds on chunks anyway' },
      { case: 'Cache hit on stale tenant dictionary', solution: 'Invalidate cache on dictionary update' },
    ],
    failureModes: [
      { mode: 'LLM service down', detect: '/health/upstreams kind=llm', recover: 'Skip rewrite + HyDE; raw retrieval; degraded=True' },
      { mode: 'Intent classifier degrades', detect: 'Eval misclassification rate', recover: 'Roll back model' },
    ],
    monitoring: ['Per-step latency', 'Cache hit rate', 'Rewrite quality eval', 'Intent classification accuracy'],
    testing: ['Drill: rewrite preserves intent on benchmark', 'Drill: HyDE improves recall on benchmark', 'Drill: cache invalidation on dict update'],
    security: ['No PII in expansion dictionary', 'Per-tenant dictionary isolated'],
    scaling: ['Cache common queries', 'Batch HyDE LLM calls'],
    maturity: {
      mvp: 'Raw query (no pre-retrieval)',
      production: 'Synonym expand + rewrite-on-demand + cache',
      enterprise: 'HyDE + intent classifier + per-tenant dictionary',
    },
    limitations: ['Latency budget caps depth', 'LLM cost grows linearly with traffic'],
    projectFit: ['retrieval-svc/app/services/pre_retrieval.py', 'mcp/tests/drill_pre_retrieval.py'],
    interviewLine: 'Pre-retrieval lifts recall cheaply: expand + rewrite + HyDE. The trade-off is latency. We gate each step on query specificity.',
  },
  // ---- 5. Post-retrieval ----
  {
    slug: 'post-retrieval',
    title: '5. Post-retrieval — rerank + filter + dedupe',
    status: 'shipped',
    coreConcept: 'Post-retrieval refines the top-K from vector search before passing to the LLM: cross-encoder rerank, deduplication, source-filter, citation-prep. Dramatically improves grounded-answer quality.',
    oneLiner: 'Post-retrieval = top-20 → top-5 with cross-encoder; cuts LLM tokens 4x and lifts answer quality.',
    fiveW: {
      what: 'A pipeline after vector search: cross-encoder rerank (relevance score per chunk), deduplication (content_hash), source-filter (per-tenant policy), citation-prep (link chunks to source docs).',
      why: 'Top-K from ANN includes noise. Cross-encoder reranks by joint relevance, lifting answer quality + cutting LLM token cost 4x.',
      where: 'retrieval-svc applies post-retrieval after Qdrant search.',
      when: 'Always for grounded RAG. Skip for keyword-only or very low SLA workloads.',
      who: 'AI/ML team owns rerank model. Retrieval team owns pipeline.',
    },
    interview30s: 'Post-retrieval refines top-20 from ANN to top-5 for the LLM. Cross-encoder rerank scores each (query, chunk) pair jointly — much higher quality than ANN scores alone. Deduplication uses content_hash. Source-filter applies per-tenant policy (e.g., only certain doc types). Citation-prep links chunks to source for the LLM to emit citations. The trade-off: 50-100ms latency, but 4x token cost reduction on the LLM call balances out.',
    coreBuildingBlocks: [
      'Cross-encoder model (BGE-reranker, ms-marco-MiniLM)',
      'Dedup by content_hash',
      'Per-tenant source-filter (allow-list / deny-list)',
      'Citation linker — chunk_id → doc_id + page',
      'Score normalization — for fusion with other signals',
    ],
    flowchart: `flowchart LR
  TOP20[Top-20 from Qdrant] --> DEDUP[Dedup by content_hash]
  DEDUP --> FILT[Per-tenant source-filter]
  FILT --> RR[Cross-encoder rerank]
  RR --> TOP5[Top-5 sorted by relevance]
  TOP5 --> CITE[Citation linker]
  CITE --> LLM[Pass to LLM with citations]`,
    sequence: `sequenceDiagram
  autonumber
  participant Ret as retrieval-svc
  participant CE as Cross-encoder
  participant LLM as LLM
  Ret->>Ret: top-20 from ANN
  Ret->>Ret: dedup by content_hash
  Ret->>Ret: filter by tenant policy
  Ret->>CE: rerank (query, top-N pairs)
  CE-->>Ret: scored pairs
  Ret->>Ret: take top-5
  Ret->>LLM: prompt with top-5 + citations`,
    coreLayers: [
      { layer: 'Dedup', responsibility: 'content_hash compare; drop duplicates from same or different docs.' },
      { layer: 'Filter', responsibility: 'Per-tenant allow/deny list on source_id, doc_type, language.' },
      { layer: 'Rerank', responsibility: 'Cross-encoder scores (query, chunk) pairs; resort.' },
      { layer: 'Citation', responsibility: 'Link chunk_id → doc_id + page + permalink for LLM citation prompt.' },
      { layer: 'Top-K cut', responsibility: 'Take top-5 (default); cut tail to control LLM token budget.' },
    ],
    problem: 'Top-K from ANN is noisy; LLM gets distracted by irrelevant chunks. Without rerank, hallucination rate spikes.',
    whyThisApproach: 'Cross-encoder rerank 4x cheaper than re-running query through full LLM. Citation linkage is required for compliance audits.',
    whenToUse: ['Always for grounded RAG', 'Compliance-required citations', 'Quality-critical answer paths'],
    whenNotToUse: ['Keyword-only retrieval', 'Sub-100ms p99 SLA without GPU', 'Cost-extreme workloads'],
    input: 'Top-20 chunks from ANN + query + tenant_id + tenant policy',
    process: ['Dedup by content_hash', 'Filter by per-tenant policy', 'Cross-encoder rerank top-N', 'Take top-5 by score', 'Link to source for citation prompt'],
    output: 'Top-5 chunks ordered by joint relevance, each with source citation metadata.',
    alternatives: [
      { name: 'No rerank (raw top-K)', tradeoff: 'Cheapest; noisy LLM input; higher hallucination' },
      { name: 'Heuristic rerank (BM25 fusion)', tradeoff: 'Cheap; limited quality lift' },
      { name: 'Full LLM rerank', tradeoff: 'Best quality; expensive; latency-prohibitive' },
    ],
    challenges: [
      'Cross-encoder GPU cost at scale',
      'Reranker model selection (multilingual vs english-only)',
      'Citation linker schema dependency',
      'Latency budget tight',
    ],
    edgeCases: [
      { case: 'All top-20 are duplicates', solution: 'Return top-1; degraded=True; LLM answers from limited context' },
      { case: 'Per-tenant filter empties result', solution: 'Honest empty response; do not relax filter' },
      { case: 'Reranker batch fails', solution: 'Fall back to ANN scores; degraded=True; alert on rate' },
    ],
    failureModes: [
      { mode: 'Reranker service down', detect: '/health/upstreams kind=reranker', recover: 'Fall back to ANN; degraded=True; alert' },
      { mode: 'Citation linker schema drift', detect: 'Drill checks chunk_id resolution', recover: 'Roll back schema; fix linker' },
    ],
    monitoring: ['Reranker latency p95', 'Top-5 score distribution', 'Filter rejection rate', 'Citation linker success rate'],
    testing: ['Drill: rerank improves NDCG@5 on benchmark', 'Drill: dedup catches content_hash duplicates', 'Drill: filter respects per-tenant policy'],
    security: ['No PII in citation snippets without redact_pii', 'Per-tenant filter on every call'],
    scaling: ['GPU pool for cross-encoder', 'Batch rerank calls', 'Cache reranker results by (query, top-K hash)'],
    maturity: {
      mvp: 'No rerank; raw top-K',
      production: 'Cross-encoder + dedup + filter + citation',
      enterprise: 'Per-tenant reranker model + multi-language + dashboard for citation accuracy',
    },
    limitations: ['Cross-encoder is GPU-bound at scale', 'Reranker model has irreducible error rate'],
    projectFit: ['retrieval-svc/app/services/post_retrieval.py', 'libs/py/documind_core/citations.py', 'mcp/tests/drill_post_retrieval.py'],
    interviewLine: 'Post-retrieval refines top-20 to top-5 with cross-encoder rerank. Dedup, filter, cite. Cuts LLM token cost 4x and lifts answer quality.',
  },
];

export default function RAGDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">RAG deep dive</h1>
          <p className="page-subtitle">
            Chunking + Hybrid retrieval — the two Python layers that drive
            answer quality more than model choice.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </>
  );
}
