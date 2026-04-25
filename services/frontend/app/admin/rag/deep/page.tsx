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
