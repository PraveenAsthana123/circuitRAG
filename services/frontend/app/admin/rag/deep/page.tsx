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
    implementationSteps: [
      { step: 'Sentence-aware split', logic: 'Sentences via regex /(?<=[.!?])\\s+/; preserve paragraph breaks.' },
      { step: 'Token-budget windows', logic: '512-1024 tokens with 10-20% overlap; respects sentence/paragraph boundaries.' },
      { step: 'Stamp metadata', logic: 'document_id + page_no + chunk_no + embedding_version on every chunk.' },
      { step: 'Section-aware optional', logic: 'For docs with clear h1/h2 structure, weight section breaks higher.' },
      { step: 'Drill: golden recall', logic: 'Sample queries → expected chunk recall ≥ target.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/ingestion-svc/app/parsers/chunker.py — sentence-aware
import re
from dataclasses import dataclass

SENT_RE = re.compile(r"(?<=[.!?])\\s+")

@dataclass
class Chunk:
    document_id: str
    page_no: int
    chunk_no: int
    text: str
    embedding_version: str

def chunk_text(text: str, doc_id: str, page_no: int = 0,
               max_tokens: int = 512, overlap_tokens: int = 64) -> list[Chunk]:
    sents = SENT_RE.split(text)
    chunks, buf, buf_tokens, n = [], [], 0, 0
    for s in sents:
        st = len(s.split())
        if buf_tokens + st > max_tokens and buf:
            chunks.append(Chunk(doc_id, page_no, n, " ".join(buf),
                                settings.embedding_version))
            n += 1
            keep, kt = [], 0
            for s2 in reversed(buf):
                kt += len(s2.split())
                keep.insert(0, s2)
                if kt >= overlap_tokens: break
            buf, buf_tokens = keep, kt
        buf.append(s); buf_tokens += st
    if buf:
        chunks.append(Chunk(doc_id, page_no, n, " ".join(buf),
                            settings.embedding_version))
    return chunks`,
    },
    realUseCase: 'Customer corpus had product manuals with deeply nested sections. Naive 512-token splits broke mid-sentence on 18% of chunks; recall@10 was 79%. Sentence-aware chunker fixed boundaries; recall hit 91%. Adding 64-token overlap caught queries that crossed chunk boundaries — recall went to 94%.',
    prosCons: {
      pros: ['Sentence-aware boundaries preserve coherence', 'Overlap catches boundary-crossing queries', 'embedding_version stamp enables zero-downtime upgrades', 'Cheap (CPU only)'],
      cons: ['Heuristic — fails on weirdly-formatted text', 'Tables and figures still hard', 'Token-counting approximation (whitespace ≠ true tokens)'],
    },
    comparison: {
      left: 'Fixed-size character chunks',
      right: 'Sentence-aware token chunks (this)',
      rows: [
        { aspect: 'Mid-sentence breaks', left: 'Common', right: 'Rare' },
        { aspect: 'Recall@10', left: '~70-80%', right: '~90-95%' },
        { aspect: 'Implementation complexity', left: 'Trivial', right: 'Modest' },
        { aspect: 'Boundary-crossing queries', left: 'Miss', right: 'Caught by overlap' },
      ],
    },
    solutions: [
      { problem: 'Mid-sentence chunk breaks', solution: 'Sentence regex split + token budget' },
      { problem: 'Boundary-crossing query miss', solution: '10-20% chunk overlap' },
      { problem: 'Embedding upgrade re-chunk needed', solution: 'embedding_version stamp + shadow index' },
      { problem: 'Tables in chunks', solution: 'Detect table → preserve as single chunk OR pass-through to format-specific parser' },
    ],
    bestPractices: {
      do: ['Sentence-aware splits', '512-1024 tokens with 10-20% overlap', 'Stamp embedding_version', 'Drill recall on golden set', 'Per-format parser feeds chunker'],
      avoid: ['Fixed-size character splits', 'No overlap', 'Mid-sentence boundaries', 'Skipping embedding_version'],
      optimize: ['Streaming chunk emission for large docs', 'Per-tenant max_tokens override', 'Cache by content_hash + chunker_version'],
    },
    antiPatterns: ['Fixed-size chunks', 'No overlap', 'No embedding_version', 'No drill on golden set'],
    testTypes: ['Drill: chunk boundary respects sentences', 'Drill: golden recall ≥ target', 'Drill: overlap correctness', 'Drill: embedding_version propagated to all chunks'],
    testScenarios: [
      { scenario: 'Long paragraph (>2000 tokens)', expected: 'Split at sentence boundaries within budget' },
      { scenario: 'Bullet list', expected: 'Each bullet preserved or grouped sensibly' },
      { scenario: 'Boundary-crossing query', expected: 'Overlap catches; chunk hit on neighbor' },
    ],
    testData: [
      { type: 'Mixed-shape corpus', example: 'Product manuals + emails + transcripts; sentence variation' },
      { type: 'Recall golden set', example: '500 (query, expected chunk_id) pairs' },
    ],
    debuggingChecklist: ['Mid-sentence break? Sentence regex broken on edge punctuation', 'Recall regression? Check overlap + chunk size', 'Boundary cross miss? Overlap too small'],
    productionIssues: [
      { issue: 'Recall dropped 18% after embedding upgrade', rootCause: 'Re-embed without re-chunk; chunks were old shape. Re-chunked + re-embedded.' },
      { issue: 'Tables retrieved as garbled', rootCause: 'Generic chunker on PDF table extracted by pdfminer. Pass tables through to a table-specific extractor.' },
    ],
    performance: ['Chunker: ~2-5ms per 1000 tokens', 'Sentence regex: trivial', 'Throughput per worker: ~50 docs/s on average'],
    costConsiderations: ['CPU-only', 'Storage: chunks ~1.2x source text (overlap)', 'Re-chunk on upgrade is bounded'],
    observability: ['Trace: per-doc chunks emitted + boundary respect rate', 'Metrics: chunks_emitted_total{format}', 'Logs: structured per doc'],
    metrics: [
      { name: 'documind_chunks_emitted_total{format}', example: 'Counter; per-format ingest rate' },
      { name: 'documind_chunk_recall_at_10{tenant}', example: 'Gauge; sampled review trends' },
      { name: 'documind_chunk_size_tokens{p}', example: 'Histogram; p50 around 512' },
    ],
    tradeoffs: [
      { decision: 'Chunk size', tradeoff: 'Small = better precision; large = better context' },
      { decision: 'Overlap ratio', tradeoff: 'High = recall + storage; low = lean' },
      { decision: 'Sentence vs paragraph splits', tradeoff: 'Sentence: finer; paragraph: more context' },
    ],
    decisionMatrix: [
      { option: 'Sentence-aware token chunks (this)', whenToUse: 'Mixed customer corpora, retrieval quality matters' },
      { option: 'Fixed-size character', whenToUse: 'POC / hackathon / homogeneous corpus' },
      { option: 'Semantic-similarity chunking', whenToUse: 'High-end RAG; willing to pay compute' },
    ],
    starStory: {
      situation: 'Initial chunker was fixed 1000-character splits. Recall@10 stuck at 73%.',
      task: 'Boost recall without re-architecting the embedding/index.',
      action: 'Sentence-aware splits + token budget + overlap. Stamped embedding_version. drill_chunker_recall_golden in CI.',
      result: 'Recall@10: 73% → 91% on first deploy. After tuning to 64-token overlap: 94%. ADR-006 documents the discipline.',
    },
    interviewTraps: ['Fixed-size character chunks', 'No overlap', 'No embedding_version stamp', 'No recall drill on golden set'],
    finalScript: 'Chunking is the most operationally-impactful Python layer in the RAG stack. Sentences via regex, packed into 512-1024 token windows with 10-20% overlap, respecting paragraph boundaries. Every chunk stamped with document_id, page_no, chunk_no, and embedding_version — last one enables zero-downtime model upgrades via shadow index. Drill measures recall on a labeled golden set; PRs that drop recall fail CI.',
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
    implementationSteps: [
      { step: 'Parallel transport calls', logic: 'Vector + graph + cache fan-out concurrently; each guarded by its own breaker.' },
      { step: 'Per-transport breaker', logic: 'vector_breaker / graph_breaker independent; one open does not cascade.' },
      { step: 'Reciprocal-rank fusion', logic: 'Combine top-K from each source; rank by 1/(k+rank); top-20 fed to rerank.' },
      { step: 'Cross-encoder rerank', logic: 'top-20 → top-5 via cross-encoder (slower but precision-critical).' },
      { step: 'degraded=True envelope', logic: 'If ANY transport breaker open, mark response degraded; inference adds disclaimer.' },
      { step: 'Cache write on success', logic: 'Hit cache by (query_hash, embedding_version); 1h TTL.' },
      { step: 'Drill: kill transport → degraded honestly', logic: 'Negative assertion: response NOT empty AND degraded=true on partial.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/inference-svc/app/services/hybrid_retriever.py
import asyncio
from libs.py.documind_core.circuit_breaker import CircuitBreaker

vector_breaker = CircuitBreaker("retrieval->qdrant", threshold=5, recovery_timeout=30)
graph_breaker = CircuitBreaker("retrieval->neo4j", threshold=5, recovery_timeout=30)

@dataclass
class RetrieveResponse:
    chunks: list[Chunk]
    degraded: bool
    sources_used: list[str]

async def hybrid_retrieve(query: str, tenant_id: str, top_k: int = 5) -> RetrieveResponse:
    sources, chunks, degraded = [], [], False

    async def fetch_vector():
        nonlocal degraded
        if not vector_breaker.allow():
            degraded = True
            return []
        try:
            vc = await qdrant.search(query, tenant_id, top_k=20)
            vector_breaker.record_success()
            sources.append("vector")
            return vc
        except Exception:
            vector_breaker.record_failure()
            degraded = True
            return []

    async def fetch_graph():
        nonlocal degraded
        if not graph_breaker.allow():
            degraded = True
            return []
        try:
            gc = await neo4j.traverse(query, tenant_id, depth=2)
            graph_breaker.record_success()
            sources.append("graph")
            return gc
        except Exception:
            graph_breaker.record_failure()
            degraded = True
            return []

    async def fetch_cache():
        cc = await redis_cache.lookup(query, tenant_id, settings.embedding_version)
        if cc:
            sources.append("cache")
        return cc or []

    v_chunks, g_chunks, c_chunks = await asyncio.gather(
        fetch_vector(), fetch_graph(), fetch_cache(),
    )

    fused = reciprocal_rank_fuse([v_chunks, g_chunks, c_chunks])
    reranked = await cross_encoder_rerank(query, fused[:20])

    return RetrieveResponse(
        chunks=reranked[:top_k],
        degraded=degraded,
        sources_used=sources,
    )`,
    },
    realUseCase: 'Customer query "policy P references which standards section?" needed graph + vector. Vector found chunks mentioning P; graph traversed P → references → S relationship to surface S sections. Reciprocal rank fusion combined both lists; cross-encoder rerank picked the top-5 most relevant. Response cited both. When Neo4j was upgraded mid-day, graph_breaker opened, vector + cache served, response carried degraded=true → user saw "partial answer (graph context unavailable)" disclaimer instead of an outage page.',
    prosCons: {
      pros: [
        'Multi-signal coverage (semantic + structured + cached)',
        'Per-transport breakers contain failures',
        'degraded=True contract makes partial answers honest',
        'Cross-encoder rerank lifts precision 4-8pp over fusion alone',
      ],
      cons: [
        'Aggregation must handle missing-source case',
        'Cross-encoder rerank adds 30-80ms p95',
        'Cache invalidation on embedding upgrade',
        'Per-transport tuning needed',
      ],
    },
    comparison: {
      left: 'Vector-only retrieval',
      right: 'Hybrid (vector + graph + cache, this)',
      rows: [
        { aspect: 'Recall@10', left: '~85%', right: '~94%' },
        { aspect: 'Multi-hop reasoning', left: 'Weak', right: 'Native via graph' },
        { aspect: 'Failure containment', left: 'All-or-nothing', right: 'Per-transport breaker' },
        { aspect: 'Latency p95', left: '~80ms', right: '~120ms' },
        { aspect: 'Cache hit savings', left: 'Manual', right: '~35% queries skip vector+graph' },
      ],
    },
    solutions: [
      { problem: 'Vector misses multi-hop relationships', solution: 'Graph traversal supplies structured context' },
      { problem: 'One slow transport drags total latency', solution: 'Per-transport breaker fast-fails the slow one' },
      { problem: 'Silent partial answers', solution: 'degraded=True propagates to inference disclaimer' },
      { problem: 'Hot queries hit DBs repeatedly', solution: 'Cache by (query_hash, embedding_version)' },
    ],
    bestPractices: {
      do: [
        'Parallel fan-out to all transports',
        'Per-transport breaker per (caller, target)',
        'Reciprocal rank fusion before rerank',
        'Cross-encoder rerank top-20 → top-5',
        'degraded=True on partial coverage',
        'Cache by (query_hash, embedding_version)',
      ],
      avoid: [
        'Sequential transport calls (slow)',
        'Single global retrieval CB',
        'Dropping degraded flag at inference',
        'Cross-encoder on full fused list (cost)',
        'Cache without embedding_version key',
      ],
      optimize: [
        'Quantize cross-encoder for inference speed',
        'Per-tenant rerank cache (query+chunk hash)',
        'Adaptive top-K based on query specificity',
      ],
    },
    antiPatterns: [
      'Sequential transport fan-out',
      'No degraded contract',
      'No per-transport breaker',
      'Cross-encoder on entire corpus',
      'Cache without embedding_version',
    ],
    testTypes: [
      'Drill: all transports up → degraded=false',
      'Drill: kill Qdrant → vector_breaker opens, others serve, degraded=true',
      'Drill: kill Neo4j → graph_breaker opens, vector+cache serve',
      'Drill: all down → empty + degraded=true (no hallucination)',
      'Drill: cache hit on hot query → bypass vector+graph',
    ],
    testScenarios: [
      { scenario: 'All transports healthy', expected: 'chunks from all; degraded=false; rerank applied' },
      { scenario: 'Qdrant unavailable', expected: 'graph + cache serve; degraded=true' },
      { scenario: 'Same query repeated', expected: 'Cache hit; bypass vector+graph; ~10ms response' },
      { scenario: 'Embedding model upgraded', expected: 'Old cache entries pruned by version key' },
    ],
    testData: [
      { type: 'Multi-source corpus', example: 'Same query findable in vector + graph + cache; coverage measured' },
      { type: 'Toxiproxy fixture', example: 'In front of Qdrant; toggleable failure mode' },
      { type: 'Recall golden set', example: '500 (query, expected chunk_ids) pairs across single-hop + multi-hop queries' },
    ],
    debuggingChecklist: [
      'Recall regression? Check sources_used; was a transport silently down?',
      'Latency spike? Per-transport p95; rerank time',
      'degraded=true unexpected? Check breaker state; verify upstream actually unreachable',
      'Cache miss for hot query? Check embedding_version + key shape',
    ],
    productionIssues: [
      { issue: 'Inference response missed degraded disclaimer', rootCause: 'New inference-svc version dropped the field. Drill caught at PR.' },
      { issue: 'Recall dropped 12pp after embedding upgrade', rootCause: 'Cache key did not include embedding_version; old entries served stale fusion. Added version to cache key.' },
      { issue: 'Cross-encoder timeout cascaded to inference 503', rootCause: 'No timeout on rerank; one slow query held the path. Added 200ms timeout + skip-rerank fallback on breach.' },
    ],
    performance: [
      'Parallel fan-out: ~80ms p95 (max of vector + graph + cache)',
      'Reciprocal rank fusion: ~10ms top-20',
      'Cross-encoder rerank: ~30-80ms top-20 → top-5',
      'Cache hit path: ~10ms total',
    ],
    costConsiderations: [
      'Cross-encoder GPU inference: ~$0.0005/query at scale',
      'Cache (Redis): negligible per query',
      'Graph + vector compute: amortized across tenants',
    ],
    observability: [
      'Trace: per-request transport decisions + outcomes',
      'Metrics: per-transport latency, breaker state, degraded rate, cache hit ratio',
      'Logs: structured with sources_used + degraded flag + correlation_id',
    ],
    metrics: [
      { name: 'documind_retrieval_degraded_total{tenant}', example: 'Counter; rate spike means transport problem' },
      { name: 'documind_retrieval_sources_used{source}', example: 'Counter; per-source coverage tracking' },
      { name: 'documind_retrieval_cache_hit_ratio', example: 'Gauge; target ≥ 0.30' },
      { name: 'documind_rerank_latency_seconds{p}', example: 'Histogram; p95 < 100ms' },
    ],
    tradeoffs: [
      { decision: 'Cross-encoder vs no rerank', tradeoff: 'Rerank: +4-8pp precision; +30-80ms latency' },
      { decision: 'Parallel vs sequential', tradeoff: 'Parallel: max-of latency; sequential: sum-of (slower)' },
      { decision: 'Cache TTL', tradeoff: 'Long: better hit rate; staleness on corpus updates' },
    ],
    decisionMatrix: [
      { option: 'Hybrid retrieval (this)', whenToUse: 'Multi-source corpora + multi-hop queries' },
      { option: 'Vector-only', whenToUse: 'Single-hop queries; no graph relationships' },
      { option: 'Keyword-only (BM25)', whenToUse: 'Highly structured queries; rare in modern RAG' },
    ],
    starStory: {
      situation: 'Customer queries needed both semantic similarity AND multi-hop relationships ("policy A references which standards?"). Vector-only recall@10 was 78%.',
      task: 'Lift recall + maintain latency budget + handle backend failures gracefully.',
      action: 'Added Neo4j graph traversal alongside Qdrant. Per-transport breakers (ADR-008). Reciprocal rank fusion. Cross-encoder rerank top-20 → top-5. Cache layer keyed by (query_hash, embedding_version). degraded=True envelope.',
      result: 'Recall@10: 78% → 94%. Latency p95: 80ms → 120ms (acceptable). Neo4j upgrade later that quarter caused zero outages — graph_breaker opened, vector+cache served, users saw partial-answer disclaimer.',
    },
    interviewTraps: [
      'Single-CB-fits-all retrieval (one transport down kills everything)',
      'Dropping degraded flag at inference',
      'Cross-encoder on full corpus instead of top-20',
      'Cache without embedding_version key',
      'No per-transport timeout',
    ],
    finalScript: 'Hybrid retrieval combines three signals fused honestly. Vector + graph + cache fan-out in parallel, each gated by its own breaker. Reciprocal rank fuses the top-K from each source into a top-20 list, then a cross-encoder rerank narrows to top-5 with precision-critical scoring. The response carries a degraded=True flag if ANY transport breaker was open during fan-out, and inference-svc honors that by adding a "partial answer" disclaimer to the user. Cache key includes embedding_version so model upgrades invalidate cleanly. Drill kills each transport in isolation and asserts the others continue serving with degraded=true — the difference between an enterprise RAG platform and a demo.',
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
    implementationSteps: [
      { step: 'Pin model + version', logic: 'embedding_model + embedding_version on every chunk + every query.' },
      { step: 'Shadow collection on upgrade', logic: 'New version embeds in parallel collection; old still serves.' },
      { step: 'Eval gate on golden set', logic: 'Recall@10 of new ≥ old (within tolerance) before flip.' },
      { step: 'Alias flip', logic: 'Atomic alias swap; new version becomes live; old retained for rollback.' },
      { step: 'Reject mismatched upsert', logic: 'Repository checks chunk.embedding_version == settings.embedding_version; reject if mismatch.' },
      { step: 'Retain old N days', logic: 'Old collection kept for 7-14 days; rollback path tested.' },
      { step: 'Drill: mismatched-version upsert rejected', logic: 'Negative assertion at API layer.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/embedder.py — version-coupled embedding pipeline
from sentence_transformers import SentenceTransformer
from libs.py.documind_core.exceptions import EmbeddingVersionMismatch

class Embedder:
    def __init__(self, model_name: str, version: str):
        self.model = SentenceTransformer(model_name)
        self.version = version
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, text: str) -> tuple[list[float], str]:
        vec = self.model.encode(text, normalize_embeddings=True).tolist()
        return vec, self.version

class ChunkRepository:
    def __init__(self, qdrant_client, expected_version: str):
        self.qdrant = qdrant_client
        self.expected_version = expected_version

    async def upsert(self, chunk: Chunk):
        if chunk.embedding_version != self.expected_version:
            raise EmbeddingVersionMismatch(
                f"chunk version {chunk.embedding_version} != "
                f"expected {self.expected_version}"
            )
        await self.qdrant.upsert(
            collection_name=f"chunks_v{self.expected_version}",
            points=[{"id": chunk.id, "vector": chunk.embedding,
                     "payload": chunk.payload}],
        )

# Shadow-index upgrade workflow
async def upgrade_embedding(old_v: str, new_v: str, eval_runner):
    new_embedder = Embedder("BAAI/bge-small-en-v1.5", new_v)
    # 1. Build shadow collection with new model
    await rebuild_shadow_collection(new_embedder, new_v)
    # 2. Eval gate
    new_recall = await eval_runner.run(version=new_v)
    old_recall = await eval_runner.run(version=old_v)
    if new_recall < old_recall - 0.02:  # 2pp tolerance
        raise EvalGateFailed(f"recall regressed: {old_recall:.3f} → {new_recall:.3f}")
    # 3. Atomic alias flip
    await qdrant.swap_alias("chunks_live", target=f"chunks_v{new_v}")
    # 4. Schedule old collection deletion (T+14 days)
    await schedule_cleanup(f"chunks_v{old_v}", days=14)`,
    },
    realUseCase: 'Customer wanted upgrade from bge-small-en-v1.5 (384d, recall@10 = 87%) to bge-large-en-v1.5 (1024d, recall@10 = 91%). Workflow: build new collection with v2 alongside v1; eval-svc compared recall@10 on golden set (4pp gain confirmed); atomic alias flip from v1 → v2; old collection retained 14 days. Total user-visible downtime: 0 seconds. Without shadow + eval gate, in-place reindex would have taken the index down for hours and a recall regression would have been invisible.',
    prosCons: {
      pros: ['Zero-downtime upgrades', 'Eval gate catches regressions BEFORE flip', 'Rollback path tested via retained old collection', 'embedding_version stamp prevents mixed upserts'],
      cons: ['2x storage during transition', 'Re-embed all chunks (compute cost)', 'Per-tenant golden set maintenance'],
    },
    comparison: {
      left: 'In-place reindex',
      right: 'Shadow + eval gate + alias flip (this)',
      rows: [
        { aspect: 'Downtime', left: 'Hours', right: 'Zero seconds' },
        { aspect: 'Regression visibility', left: 'Production users', right: 'Eval gate before flip' },
        { aspect: 'Rollback', left: 'Re-embed (slow)', right: 'Alias flip back (instant)' },
        { aspect: 'Storage during upgrade', left: '1x', right: '2x (transient)' },
        { aspect: 'Compliance evidence', left: 'None', right: 'Eval report + audit row' },
      ],
    },
    solutions: [
      { problem: 'Vendor model deprecated', solution: 'Shadow-index successor; eval gate; flip when ready' },
      { problem: 'Mixed-version vectors in store', solution: 'Repository rejects mismatched-version upsert' },
      { problem: 'Recall drop after upgrade', solution: 'Eval gate enforces tolerance; alias flip blocked' },
      { problem: 'Vendor outage on cloud embedder', solution: 'Cache embeddings + fallback to local model' },
    ],
    bestPractices: {
      do: [
        'embedding_version stamp on every chunk + every query',
        'Shadow collection for any upgrade',
        'Eval gate on golden set before alias flip',
        'Atomic alias swap (not rolling)',
        'Retain old collection 7-14 days for rollback',
        'Drill: mismatched-version upsert rejected',
      ],
      avoid: [
        'In-place reindex (downtime + no rollback)',
        'Skipping eval gate (silent regression)',
        'No version stamp (mixed vectors silently)',
        'Deleting old collection same-day as flip',
      ],
      optimize: [
        'Quantize new model to int8 for memory + cost',
        'Per-tenant golden set for tenant-relevant eval',
        'Batch re-embed across multiple workers',
      ],
    },
    antiPatterns: [
      'In-place reindex',
      'No eval gate before flip',
      'No embedding_version stamp',
      'Same-day cleanup of old collection',
      'Mixed-version retrieval',
    ],
    testTypes: [
      'Drill: mismatched-version upsert raises EmbeddingVersionMismatch',
      'Drill: shadow collection built before alias flip',
      'Drill: eval gate blocks flip on regression > tolerance',
      'Drill: retrieval against alias finds new vectors post-flip',
      'Drill: rollback alias-swap restores old version',
    ],
    testScenarios: [
      { scenario: 'New model exhibits 2pp recall regression', expected: 'Eval gate fails; alias flip blocked' },
      { scenario: 'Engineer manually upserts wrong-version vector', expected: 'EmbeddingVersionMismatch raised' },
      { scenario: 'Customer eval set highlights tenant-specific regression', expected: 'Per-tenant gate; flip deferred for that tenant' },
      { scenario: 'Vendor deprecates model', expected: 'Shadow-index successor; eval; flip' },
    ],
    testData: [
      { type: 'Eval golden set', example: '500 (query, expected chunk_ids) per tenant for recall@10' },
      { type: 'Mismatched-version probe', example: 'Synthetic chunk with old version + new index target; reject expected' },
      { type: 'Shadow collection fixture', example: '10K chunks re-embedded with new model; alias swap rehearsed' },
    ],
    debuggingChecklist: [
      'Mismatched version error? Compare chunk.embedding_version + repository.expected_version',
      'Shadow build slow? Parallelize across workers + GPU',
      'Eval regression unexpected? Sample golden set; check tenant-specific patterns',
      'Alias flip succeeded but retrieval still old? Cache invalidation by version key',
    ],
    productionIssues: [
      { issue: 'Recall dropped 18pp after upgrade', rootCause: 'Eval gate not enforced; engineer flipped without running. Hard CI gate added.' },
      { issue: 'Mixed-version vectors found in collection', rootCause: 'Manual upsert script bypassed repository check. Added DB-level constraint.' },
      { issue: 'Rollback failed because old collection deleted', rootCause: 'Cleanup ran same-day as flip. Changed retention to 14 days minimum.' },
    ],
    performance: [
      'Shadow re-embed: ~30 min per 1M chunks on A100',
      'Eval run: ~30s for 500-item golden set',
      'Alias flip: < 100ms (atomic in Qdrant)',
      'Retrieval against new alias: same as old (no overhead)',
    ],
    costConsiderations: [
      'Re-embed compute: dominant cost (~$10-100 per 1M chunks on cloud GPU)',
      'Storage: 2x during transition (transient)',
      'Eval compute: small (~$0.50 per run)',
    ],
    observability: [
      'Trace: per-upgrade workflow with shadow + eval + flip + cleanup',
      'Metrics: embedding_version_mismatch_total, eval_recall per version, alias_flip_total',
      'Logs: structured per upgrade phase',
      'Audit: hash-chained per upgrade; admin reconstruction',
    ],
    metrics: [
      { name: 'documind_embedding_version_mismatch_total{tenant}', example: 'Counter; alert at any > 0' },
      { name: 'documind_eval_recall_at_10{embedding_version}', example: 'Gauge per release; alert on regression' },
      { name: 'documind_alias_flip_total{outcome}', example: 'Counter; outcome=success|blocked-eval|rolled-back' },
      { name: 'documind_shadow_index_build_duration_seconds{tenant,p}', example: 'Histogram; trend per million chunks' },
    ],
    tradeoffs: [
      { decision: 'Shadow vs in-place', tradeoff: 'Shadow: 0 downtime + 2x storage; in-place: hours of downtime + risk' },
      { decision: 'Eval tolerance', tradeoff: 'Tight: catches regressions; blocks legitimate small drops' },
      { decision: 'Old retention', tradeoff: 'Long: rollback safety; storage cost' },
    ],
    decisionMatrix: [
      { option: 'Shadow + eval + alias (this)', whenToUse: 'Production; uptime matters; recall regressions costly' },
      { option: 'In-place reindex', whenToUse: 'Hackathon; single-tenant POC' },
      { option: 'Rolling re-embed without alias', whenToUse: 'Never (mixed-version retrieval)' },
    ],
    starStory: {
      situation: 'bge-small was reaching its ceiling; bge-large promised +4pp recall but in-place upgrade meant hours of downtime + no rollback.',
      task: 'Upgrade to bge-large with zero downtime + rollback path + eval gate.',
      action: 'Built shadow collection with new model. Eval gate ran on golden set; +4pp confirmed. Atomic alias flip. Old collection retained 14 days. drill_embedding_version_coupling locked discipline.',
      result: 'Zero downtime. +4pp recall measured post-flip. Pattern adopted across 3 tenants. Rollback drill rehearsed quarterly.',
    },
    interviewTraps: [
      'In-place reindex (downtime + no rollback)',
      'No embedding_version stamp',
      'Skipping eval gate',
      'Same-day deletion of old collection',
      'Per-tenant golden set neglected',
    ],
    finalScript: 'Embedding upgrade is shadow-collection + eval gate + alias flip. Never in-place. Build new collection with new model in parallel. Eval gate compares recall@10 on golden set; flip blocked if regression beyond tolerance. Atomic alias swap takes new version live in milliseconds. Old collection retained 7-14 days for rollback. Repository rejects mismatched-version upsert at the API layer — drill verifies. Per-tenant golden sets handle tenant-specific drift. The non-negotiable rule: every chunk + every query carries embedding_version, and the version is the upgrade contract.',
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
    implementationSteps: [
      { step: 'Detect query intent', logic: 'Classify single-hop / multi-hop / definitional / acronym-heavy — drives strategy.' },
      { step: 'Expand abbreviations', logic: 'Domain dictionary: BHP → "bottom-hole pressure"; SOC2 → "Service Organization Control 2".' },
      { step: 'Rewrite ambiguous queries', logic: 'LLM rewrite for clarity; keep original alongside.' },
      { step: 'HyDE (hypothetical doc embedding)', logic: 'LLM generates candidate answer; embed + retrieve neighbors of that.' },
      { step: 'Multi-query retrieval', logic: 'Generate 3-5 paraphrased queries; union results.' },
      { step: 'Latency budget gate', logic: 'Skip HyDE if simple query; skip multi-query if specific query.' },
      { step: 'Drill: recall lift on multi-hop golden set', logic: 'Hard gate on +Npp recall before deploy.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/retrieval-svc/app/services/pre_retrieval.py
from libs.py.documind_core.llm import LLMClient

DOMAIN_ABBREV = {
    "BHP": "bottom-hole pressure",
    "SOC2": "Service Organization Control 2",
    "PII": "personally identifiable information",
}

@dataclass
class QueryStrategy:
    intent: str  # single-hop | multi-hop | definitional | acronym
    apply_hyde: bool
    apply_multi_query: bool
    rewrite: bool

async def classify(query: str, llm: LLMClient) -> QueryStrategy:
    """LLM-classify query intent + decide which steps apply."""
    intent = await llm.classify(query, labels=["single-hop","multi-hop","definitional","acronym"])
    return QueryStrategy(
        intent=intent,
        apply_hyde=intent in ("multi-hop", "definitional"),
        apply_multi_query=intent in ("multi-hop",),
        rewrite=intent in ("definitional",),
    )

async def pre_retrieve(query: str, llm: LLMClient) -> list[str]:
    """Returns list of candidate queries to fan out across retrieval."""
    candidates = [query]
    # Expand abbreviations
    for abbr, full in DOMAIN_ABBREV.items():
        if abbr in query.split():
            candidates.append(query.replace(abbr, full))

    strategy = await classify(query, llm)

    if strategy.rewrite:
        rewritten = await llm.rewrite(query, instruction="Make this clearer")
        candidates.append(rewritten)

    if strategy.apply_hyde:
        hyde_doc = await llm.generate(
            f"Write a paragraph that would answer: {query}",
            max_tokens=200,
        )
        candidates.append(hyde_doc)

    if strategy.apply_multi_query:
        paraphrases = await llm.paraphrase(query, n=3)
        candidates.extend(paraphrases)

    # Dedupe + cap to budget
    return list(dict.fromkeys(candidates))[:6]`,
    },
    realUseCase: 'Customer queries had heavy acronyms ("BHP measurements vs SPP at completion"). Without expansion, vector recall@10 was 64% on multi-hop. Adding domain abbreviation expansion + HyDE lifted recall@10 to 89% on the same golden set. Latency cost: +180ms p95 (acceptable for the recall gain). Single-hop simple queries skip HyDE/multi-query via the gate, keeping their latency budget intact.',
    prosCons: {
      pros: ['Recall lift +15-25pp on hard queries', 'Domain abbreviations close the vocabulary gap', 'Latency gating per query specificity', 'Cheap (LLM calls << GPU rerank cost)'],
      cons: ['LLM call adds 100-300ms latency', 'HyDE depends on LLM quality (hallucination risk)', 'Multi-query inflates retrieval cost'],
    },
    comparison: {
      left: 'No pre-retrieval (raw query)',
      right: 'Expansion + rewrite + HyDE + multi-query (this)',
      rows: [
        { aspect: 'Recall@10 on multi-hop', left: '~65%', right: '~88%' },
        { aspect: 'Recall@10 on acronym-heavy', left: '~60%', right: '~85%' },
        { aspect: 'Latency p95', left: '~80ms', right: '~260ms' },
        { aspect: 'LLM token cost per query', left: '$0', right: '~$0.001' },
      ],
    },
    solutions: [
      { problem: 'Acronym-heavy queries miss', solution: 'Domain abbreviation dictionary + expansion' },
      { problem: 'Ambiguous phrasing', solution: 'LLM rewrite alongside original' },
      { problem: 'Multi-hop queries', solution: 'HyDE + multi-query paraphrases' },
      { problem: 'Latency for simple queries', solution: 'Intent classifier gates expensive steps' },
    ],
    bestPractices: {
      do: [
        'Domain abbreviation dictionary maintained',
        'Intent-classifier gates HyDE / multi-query',
        'Cap candidate queries to budget (≤6)',
        'Dedupe candidates before fan-out',
        'Drill recall lift per query type',
      ],
      avoid: [
        'HyDE on every query (cost + latency)',
        'Multi-query without dedup (retrieval flood)',
        'Expansion without intent gating',
        'No domain abbreviation maintenance',
      ],
      optimize: [
        'Cache LLM rewrites by query_hash',
        'Smaller cheaper LLM for rewrite (Mistral-7B fine)',
        'Parallel candidate-query fan-out',
      ],
    },
    antiPatterns: [
      'HyDE on every query',
      'No latency budget gate',
      'No dedup before fan-out',
      'Multi-query without budget cap',
    ],
    testTypes: [
      'Drill: acronym-heavy query → expansion fires',
      'Drill: multi-hop query → HyDE + multi-query',
      'Drill: simple query → skip HyDE',
      'Drill: recall lift ≥ +Npp on golden set per query type',
    ],
    testScenarios: [
      { scenario: 'Query "BHP at well X"', expected: 'Expanded to "bottom-hole pressure at well X"' },
      { scenario: 'Multi-hop query', expected: 'HyDE + multi-query candidates generated; fan-out' },
      { scenario: 'Simple definitional', expected: 'Rewrite only; HyDE skipped' },
      { scenario: 'Latency budget breach', expected: 'Skip multi-query; rerank top-K only' },
    ],
    testData: [
      { type: 'Acronym corpus', example: '500 acronym-heavy queries; expansion measured' },
      { type: 'Multi-hop golden set', example: '300 multi-hop queries with expected chunks; recall measured' },
      { type: 'Latency benchmark', example: 'p50/p95 across query intents; gate tuning' },
    ],
    debuggingChecklist: [
      'Recall not lifting? Check abbreviation dict + intent classifier',
      'Latency spike? HyDE running on simple queries; check gate',
      'HyDE hallucinating? Check LLM quality + prompt',
      'Multi-query results too narrow? Increase paraphrase count',
    ],
    productionIssues: [
      { issue: 'Latency p95 doubled after pre-retrieval rollout', rootCause: 'HyDE running on every query; intent gate was disabled for testing.' },
      { issue: 'Recall regressed despite expansion', rootCause: 'Abbreviation dict had outdated entries; one tenant\'s domain shifted. Per-tenant override added.' },
      { issue: 'HyDE leaked customer-specific PII into hypothetical doc', rootCause: 'Prompt injection from query. Added Guardrails AI input filter pre-HyDE.' },
    ],
    performance: [
      'Intent classify: ~50ms p95',
      'LLM rewrite: ~80-150ms p95',
      'HyDE generation: ~150-300ms p95',
      'Multi-query paraphrase: ~100-200ms (parallel)',
      'Total pre-retrieve: ~150-300ms p95 with gating',
    ],
    costConsiderations: [
      'LLM calls: ~$0.0005-0.002 per query',
      'Cache hits: ~30% on rewrite step',
      'Smaller cheaper model for rewrite (~$0.0002)',
    ],
    observability: [
      'Trace: per-query strategy + candidate count',
      'Metrics: pre_retrieve_steps_applied, latency per step, recall lift per intent',
      'Logs: structured with intent + candidates count',
    ],
    metrics: [
      { name: 'documind_pre_retrieve_strategy{intent}', example: 'Counter; per-intent volume' },
      { name: 'documind_pre_retrieve_latency_seconds{step,p}', example: 'Histogram per step (classify/rewrite/hyde/multi)' },
      { name: 'documind_pre_retrieve_recall_lift_pp{intent}', example: 'Gauge; tracked per release' },
    ],
    tradeoffs: [
      { decision: 'HyDE always vs gated', tradeoff: 'Always = uniform recall; gated = lower latency on simple queries' },
      { decision: 'Multi-query count', tradeoff: 'More = better recall; more LLM cost + retrieval volume' },
      { decision: 'Cheap vs powerful rewrite LLM', tradeoff: 'Cheap = fast; powerful = better rewrite quality' },
    ],
    decisionMatrix: [
      { option: 'Full pre-retrieve (this)', whenToUse: 'Multi-hop or acronym-heavy domains' },
      { option: 'Expansion only', whenToUse: 'Acronym domains; latency-tight' },
      { option: 'No pre-retrieve', whenToUse: 'Simple single-hop queries dominant' },
    ],
    starStory: {
      situation: 'Customer corpus was acronym-heavy + multi-hop; vanilla retrieval recall@10 was 64%.',
      task: 'Lift recall without blowing latency budget.',
      action: 'Built pre-retrieve pipeline: domain abbreviation expansion, intent classifier, LLM rewrite for ambiguous, HyDE for multi-hop, multi-query paraphrases. Gated each step on intent. drill_pre_retrieval_recall_lift in CI.',
      result: 'Recall@10: 64% → 89%. Latency p95: 80ms → 260ms (acceptable). Per-intent gating keeps simple queries fast.',
    },
    interviewTraps: [
      'HyDE on every query (cost + latency)',
      'No intent gating',
      'Abbreviation dict not maintained',
      'No prompt-injection filter on HyDE',
    ],
    finalScript: 'Pre-retrieval lifts recall cheaply: expand abbreviations, rewrite ambiguous queries, HyDE for multi-hop, multi-query paraphrases for complex intent. Each step is gated by an intent classifier so simple queries skip the expensive paths. Domain abbreviation dictionary is per-tenant configurable. HyDE has a prompt-injection filter to prevent jailbreak in the hypothetical doc. Drill measures recall lift per query type on a labeled golden set; PRs that drop recall fail CI. The trade-off is latency — recall@10 lifts 25pp at the cost of 150-180ms p95.',
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
    implementationSteps: [
      { step: 'Cross-encoder rerank', logic: 'Top-20 fused → top-5 ranked by query-chunk pair score (slow but precise).' },
      { step: 'Dedup near-duplicates', logic: 'Hash by chunk content prefix; remove ≥0.95 similarity pairs.' },
      { step: 'Filter by metadata', logic: 'Tenant filter, date filter, doc-type filter applied per query.' },
      { step: 'Citation pruning', logic: 'Drop chunks scoring < threshold; keep only those that will be cited.' },
      { step: 'Citation deadline budget', logic: 'If LLM hasn\'t cited by token N, signal interrupt.' },
      { step: 'Cache rerank scores', logic: 'Key = (query_hash, chunk_id, embedding_version); 1h TTL.' },
      { step: 'Drill: rerank precision lift on golden set', logic: 'Hard gate on +Npp precision@5.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/retrieval-svc/app/services/post_retrieval.py
from sentence_transformers import CrossEncoder
import hashlib

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-12-v2")

@dataclass
class RerankedChunk:
    chunk: Chunk
    score: float

async def rerank_and_filter(
    query: str, chunks: list[Chunk], top_k: int = 5,
    score_threshold: float = 0.3,
) -> list[RerankedChunk]:
    """Top-20 → top-K via cross-encoder; dedupe + filter + threshold."""
    # Cache lookup
    cached = await rerank_cache.lookup(query, [c.id for c in chunks])
    fresh = [c for c in chunks if c.id not in cached]

    # Score fresh pairs
    pairs = [(query, c.text) for c in fresh]
    scores = reranker.predict(pairs) if pairs else []

    all_scored = [
        RerankedChunk(c, s) for c, s in zip(fresh, scores)
    ] + [RerankedChunk(c, cached[c.id]) for c in chunks if c.id in cached]

    # Persist new scores
    await rerank_cache.store({
        c.chunk.id: c.score for c in all_scored if c.chunk.id not in cached
    })

    # Threshold filter (drop low-relevance noise)
    above = [r for r in all_scored if r.score >= score_threshold]

    # Dedupe near-duplicates by content prefix hash
    seen_prefixes = set()
    deduped = []
    for r in sorted(above, key=lambda x: -x.score):
        prefix = hashlib.sha256(r.chunk.text[:200].encode()).hexdigest()[:16]
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        deduped.append(r)

    return deduped[:top_k]`,
    },
    realUseCase: 'Without rerank, top-20 from fusion was fed directly to LLM — average prompt was 8K tokens, cost ~$0.04/query, precision@5 was 62% (3 of 5 chunks were redundant or off-topic). Adding cross-encoder rerank + threshold + dedup: top-5 averaged 2K tokens, cost dropped to ~$0.01/query, precision@5 lifted to 87%. The 4x cost reduction paid for the cross-encoder GPU within a week.',
    prosCons: {
      pros: ['Precision@5 lifts +20-25pp', 'LLM token cost drops 4x (smaller prompt)', 'Dedup removes redundant context noise', 'Citation pruning improves answer quality'],
      cons: ['Cross-encoder is GPU-bound (~30-80ms p95)', 'Cache invalidation on embedding upgrade', 'Threshold tuning per tenant'],
    },
    comparison: {
      left: 'Top-20 directly to LLM',
      right: 'Rerank + dedup + threshold + top-5 (this)',
      rows: [
        { aspect: 'Precision@5', left: '~62%', right: '~87%' },
        { aspect: 'Prompt size', left: '~8K tokens', right: '~2K tokens' },
        { aspect: 'Cost per query', left: '~$0.04', right: '~$0.01' },
        { aspect: 'Latency added', left: '0', right: '+30-80ms p95' },
      ],
    },
    solutions: [
      { problem: 'LLM gets too many redundant chunks', solution: 'Cross-encoder rerank + dedup' },
      { problem: 'Off-topic chunks bloat prompt', solution: 'Score threshold cuts low-relevance' },
      { problem: 'Hot queries hit reranker repeatedly', solution: 'Cache scores by (query_hash, chunk_id)' },
      { problem: 'No-citation hallucination', solution: 'Citation deadline signal interrupts at token N' },
    ],
    bestPractices: {
      do: [
        'Cross-encoder rerank top-20 → top-5',
        'Score threshold (e.g., 0.3) cuts low-relevance',
        'Dedupe by content prefix hash',
        'Cache by (query_hash, chunk_id, embedding_version)',
        'Citation deadline signal in inference',
      ],
      avoid: [
        'Cross-encoder on entire corpus',
        'No threshold (low-relevance noise pollutes prompt)',
        'No dedup (redundant chunks waste tokens)',
        'Cache without embedding_version key',
      ],
      optimize: [
        'Quantize cross-encoder to int8',
        'GPU pool with bounded concurrency',
        'Per-tenant threshold tuning',
        'Parallel rerank + dedup',
      ],
    },
    antiPatterns: [
      'Cross-encoder on full corpus',
      'No score threshold',
      'No dedup',
      'No cache',
      'Citation deadline ignored',
    ],
    testTypes: [
      'Drill: rerank lifts precision@5 by ≥ Npp on golden set',
      'Drill: dedup removes ≥0.95-similarity chunks',
      'Drill: threshold filter rejects low-relevance',
      'Drill: cache hits skip recomputation',
      'Drill: citation deadline interrupts at token N',
    ],
    testScenarios: [
      { scenario: 'Top-20 has 5 near-duplicates', expected: 'Dedup removes 4; top-5 has unique chunks' },
      { scenario: 'Low-relevance chunk above threshold', expected: 'Filter rejects; not in top-5' },
      { scenario: 'Hot query repeated', expected: 'Cache hit; skip rerank compute' },
      { scenario: 'LLM no citation by token 200', expected: 'Citation deadline interrupts; output truncated' },
    ],
    testData: [
      { type: 'Precision golden set', example: '500 (query, expected top-5) pairs; precision@5 measured' },
      { type: 'Near-duplicate corpus', example: 'Synthetic chunks 95-99% similar; dedup tested' },
      { type: 'Low-relevance probe', example: 'Off-topic chunks alongside relevant; threshold tested' },
    ],
    debuggingChecklist: [
      'Precision low? Check threshold + dedup',
      'Latency spike? GPU pool saturation',
      'Cache miss for hot query? Check key shape + TTL',
      'Citation deadline never fires? Check signal wiring in stream',
    ],
    productionIssues: [
      { issue: 'Reranker hung on 1 query, blocking pool', rootCause: 'No timeout. Added 200ms timeout + skip-rerank fallback.' },
      { issue: 'Threshold filtered out tenant-specific high-relevance', rootCause: 'Global threshold; tenant\'s domain skewed scores. Per-tenant override added.' },
      { issue: 'Cache served stale scores after embedding upgrade', rootCause: 'Cache key missed embedding_version. Added version key + retroactive eviction.' },
    ],
    performance: [
      'Cross-encoder rerank: ~30-80ms p95 for top-20 (GPU)',
      'Dedup hash: ~1ms',
      'Threshold filter: O(n)',
      'Cache hit path: ~5-10ms',
    ],
    costConsiderations: [
      'GPU rerank: ~$0.0005 per query at scale',
      'Cache (Redis): negligible per query',
      'LLM token savings: ~75% reduction in prompt tokens',
    ],
    observability: [
      'Trace: per-query rerank score distribution + dedup count',
      'Metrics: precision@5, prompt_tokens, rerank_latency, cache_hit_ratio',
      'Logs: structured with chunks_kept_count + dropped_below_threshold',
    ],
    metrics: [
      { name: 'documind_rerank_precision_at_5{tenant}', example: 'Gauge; sampled review trends' },
      { name: 'documind_rerank_latency_seconds{p}', example: 'Histogram; p95 < 100ms' },
      { name: 'documind_rerank_cache_hit_ratio', example: 'Gauge; target ≥ 0.30' },
      { name: 'documind_chunks_dropped_below_threshold_total', example: 'Counter; high count = noisy retrieval' },
    ],
    tradeoffs: [
      { decision: 'Top-K size', tradeoff: 'Smaller = lower cost; risk of missing context' },
      { decision: 'Threshold tightness', tradeoff: 'Tight = pure context; may drop borderline relevant' },
      { decision: 'Dedup similarity threshold', tradeoff: 'Aggressive = no redundancy; may lose nuance' },
    ],
    decisionMatrix: [
      { option: 'Cross-encoder rerank (this)', whenToUse: 'Production with quality + cost tight' },
      { option: 'No rerank', whenToUse: 'POC or cost-sensitive demo' },
      { option: 'LLM-as-reranker', whenToUse: 'Smaller corpus; no cross-encoder infra' },
    ],
    starStory: {
      situation: 'LLM was receiving top-20 chunks at ~8K tokens per prompt; cost $0.04/query; precision@5 was 62%.',
      task: 'Cut cost + lift precision without sacrificing recall.',
      action: 'Added cross-encoder rerank top-20 → top-5. Score threshold 0.3. Dedup by content prefix hash. Cache by (query, chunk, embedding_version). Citation deadline signal.',
      result: 'Cost dropped to $0.01/query (4x). Precision@5: 62% → 87%. GPU paid for itself in a week. Pattern in ADR-011.',
    },
    interviewTraps: [
      'Cross-encoder on entire corpus',
      'No threshold filter',
      'No dedup',
      'Cache without embedding_version',
      'No citation deadline',
    ],
    finalScript: 'Post-retrieval refines top-20 to top-5 via cross-encoder rerank. Score threshold drops low-relevance noise. Dedup by content prefix hash removes near-duplicates. Cache scores by (query_hash, chunk_id, embedding_version) — 30%+ hit rate on hot queries. Citation deadline signal interrupts the LLM stream if no citation by token N. The wins are concrete: precision@5 lifts 62% → 87%, prompt tokens drop 4x, cost-per-query drops 4x. Drill measures precision@5 on a labeled golden set; PRs that drop precision fail CI.',
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
