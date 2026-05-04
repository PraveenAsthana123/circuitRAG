/**
 * Vectorless RAG with Elasticsearch — index page.
 *
 * Per CLAUDE.md §39 (RAG architecture) + §49 (compose-footer). This
 * is a Server Component (default, no 'use client') because it's
 * static documentation — no interactive state or live ES queries
 * in Stage-1. Stage-2 wires a query playground via /api/v1/retrieve
 * with strategy=vectorless.
 */

import Link from 'next/link';

const TOPICS = [
  {
    id: 'what',
    title: 'What is vectorless RAG?',
    body: (
      <>
        <p>
          Vectorless RAG retrieves documents <strong>without</strong> embedding-based similarity search. Instead of dense vectors and ANN, it uses Elasticsearch's BM25 + structured filters + boolean queries. The LLM still sees retrieved chunks as context — only the retrieval step changes.
        </p>
        <p>
          Why "vectorless" is a real architecture (not a regression):
        </p>
        <ul>
          <li><strong>No embedding-model lock-in.</strong> Re-embedding 50M chunks on a model upgrade costs money + time. Vectorless skips that.</li>
          <li><strong>Exact-term recall.</strong> "ABC-123-XYZ" product code or "ISIN US0378331005" matches deterministically. Vector similarity may miss exact strings that are far in embedding space.</li>
          <li><strong>Tenant-scoped + filter-heavy queries.</strong> Elasticsearch filters on tenant_id / date / doc_type before BM25 scoring is cheap; vector ANN before metadata-filter is expensive.</li>
          <li><strong>Auditable scoring.</strong> BM25 has explainable per-term scores. Cosine-similarity in 1024-d is a single number with no per-feature breakdown.</li>
        </ul>
      </>
    ),
  },
  {
    id: 'when',
    title: 'When vectorless beats vector',
    body: (
      <>
        <p>The decision matrix:</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              <th style={{ textAlign: 'left', padding: 6 }}>Use case</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Vectorless (ES)</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Vector (Qdrant)</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Winner</th>
            </tr>
          </thead>
          <tbody>
            <tr><td style={{ padding: 6 }}>Exact identifier match (SKU, ISIN, CVE-IDs)</td><td>✅ deterministic</td><td>⚠️ approximate</td><td>vectorless</td></tr>
            <tr><td style={{ padding: 6 }}>Synonym / paraphrase recall</td><td>⚠️ needs synonyms file</td><td>✅ semantic</td><td>vector</td></tr>
            <tr><td style={{ padding: 6 }}>Heavy metadata filtering</td><td>✅ filter-then-score</td><td>⚠️ filter-then-ANN slow</td><td>vectorless</td></tr>
            <tr><td style={{ padding: 6 }}>Cross-language retrieval</td><td>⚠️ per-language analyzers</td><td>✅ multilingual embeddings</td><td>vector</td></tr>
            <tr><td style={{ padding: 6 }}>Cost (50M chunks)</td><td>~storage only</td><td>+embedding cost + GPU index</td><td>vectorless</td></tr>
            <tr><td style={{ padding: 6 }}>Conceptual similarity</td><td>❌ keyword-bound</td><td>✅ embedding-bound</td><td>vector</td></tr>
            <tr><td style={{ padding: 6 }}>Hybrid (rerank both)</td><td>BM25 floor</td><td>vector recall</td><td>BOTH</td></tr>
          </tbody>
        </table>
        <p style={{ marginTop: 12 }}>
          <strong>Default recommendation:</strong> hybrid (BM25 + vector + reciprocal rank fusion). Pure vectorless wins for regulated domains where audit trails matter and exact-term recall is non-negotiable. Pure vector wins for open-ended question-answering.
        </p>
      </>
    ),
  },
  {
    id: 'architecture',
    title: 'Architecture — how vectorless slots into the 11-layer stack',
    body: (
      <>
        <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem', overflow: 'auto' }}>{`
User Query
  ↓
1. API Gateway     (auth, tenant)
  ↓
2. Agent Router    (intent + risk classify)
  ↓
3. PolisAI         (allowed_tools check; "retrieve:vectorless" scope)
  ↓
4. Council         (decides retrieval strategy: vector | vectorless | hybrid)
  ↓
5. RetrievalService.Retrieve(strategy="vectorless", filters={tenant_id, ...})
  ↓
6. Elasticsearch query:
     {
       "query": {
         "bool": {
           "must":   [{"match": {"text": "<query>"}}],
           "filter": [
             {"term": {"tenant_id": "<tenant>"}},
             {"term": {"doc_type":  "regulation"}},
             {"range": {"doc_date": {"gte": "2024-01-01"}}}
           ]
         }
       },
       "size": 20,
       "_source": ["chunk_id", "doc_id", "text", "page"]
     }
  ↓
7. (Optional) cross-encoder rerank — keep top-K
  ↓
8. Build LLM prompt with retrieved chunks + citation map
  ↓
9. Council's LLM answer
`.trim()}</pre>
        <p style={{ marginTop: 12 }}>
          The vectorless path is parallel to the vector path through the same{' '}
          <code>RetrievalService</code> contract — only the strategy field changes. Drill <code>drill_retrieval_strategy_router.py</code> locks both directions.
        </p>
      </>
    ),
  },
  {
    id: 'queries',
    title: 'Elasticsearch query patterns',
    body: (
      <>
        <h4>1. Plain BM25 with tenant filter</h4>
        <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem' }}>{`
GET /documind-chunks/_search
{
  "query": {
    "bool": {
      "must":   [{"match": {"text": "circuit breaker pattern"}}],
      "filter": [{"term": {"tenant_id": "tenant-a"}}]
    }
  },
  "size": 20
}`.trim()}</pre>

        <h4>2. Phrase match (exact term)</h4>
        <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem' }}>{`
GET /documind-chunks/_search
{
  "query": {
    "bool": {
      "must":   [{"match_phrase": {"text": "ISIN US0378331005"}}],
      "filter": [{"term": {"tenant_id": "tenant-a"}}]
    }
  }
}`.trim()}</pre>

        <h4>3. Multi-field weighted</h4>
        <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem' }}>{`
GET /documind-chunks/_search
{
  "query": {
    "multi_match": {
      "query":  "interest rate swap",
      "fields": ["title^3", "summary^2", "text^1"],
      "type":   "best_fields"
    }
  }
}`.trim()}</pre>

        <h4>4. Custom analyzer for code-aware tokenization</h4>
        <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem' }}>{`
PUT /documind-chunks
{
  "settings": {
    "analysis": {
      "analyzer": {
        "code_aware": {
          "tokenizer": "whitespace",
          "filter": ["lowercase", "asciifolding", "edge_ngram_2_8"]
        }
      },
      "filter": {
        "edge_ngram_2_8": {
          "type": "edge_ngram", "min_gram": 2, "max_gram": 8
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "text": {"type": "text", "analyzer": "code_aware"}
    }
  }
}`.trim()}</pre>

        <h4>5. Hybrid via Reciprocal Rank Fusion (RRF)</h4>
        <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem' }}>{`
# ES 8.8+ supports native RRF
GET /documind-chunks/_search
{
  "rank": {
    "rrf": {
      "window_size": 50,
      "rank_constant": 20
    }
  },
  "query":  {"match": {"text": "<query>"}},
  "knn":    {"field": "embedding", "query_vector": [...], "k": 50}
}`.trim()}</pre>
      </>
    ),
  },
  {
    id: 'index-mapping',
    title: 'Recommended index mapping',
    body: (
      <pre style={{ background: '#f5f5f5', padding: 12, fontSize: '0.85rem', overflow: 'auto' }}>{`
PUT /documind-chunks
{
  "settings": {
    "number_of_shards":   3,
    "number_of_replicas": 1,
    "refresh_interval":   "5s",
    "analysis": {
      "analyzer": { "default": { "type": "english" } }
    }
  },
  "mappings": {
    "properties": {
      "chunk_id":     {"type": "keyword"},
      "doc_id":       {"type": "keyword"},
      "tenant_id":    {"type": "keyword"},   /* tenant isolation */
      "doc_type":     {"type": "keyword"},
      "doc_date":     {"type": "date"},
      "page":         {"type": "integer"},
      "text":         {"type": "text", "analyzer": "english"},
      "title":        {"type": "text", "analyzer": "english"},
      "summary":      {"type": "text", "analyzer": "english"},
      "metadata":     {"type": "object", "dynamic": true},
      "embedding":    {"type": "dense_vector", "dims": 1024, "index": true,
                       "similarity": "cosine"}  /* present for hybrid mode */
    }
  }
}`.trim()}</pre>
    ),
  },
  {
    id: 'gotchas',
    title: 'Gotchas + operator playbook',
    body: (
      <>
        <ul>
          <li><strong>Always filter on tenant_id BEFORE the BM25 must clause</strong> — the planner short-circuits per-tenant + RLS leaks are caught.</li>
          <li><strong>Use <code>refresh_interval: 5s</code></strong> in prod, not the default 1s — heavy re-indexing kills CPU.</li>
          <li><strong>Watch your shard count.</strong> 3 primary shards × 1 replica = 6 shards per index. With 100 indices that's 600 shards on a 3-node cluster — too many. Use ILM (index lifecycle management).</li>
          <li><strong>Synonyms file matters.</strong> Without one, "regulation" doesn't recall "rule" or "directive". Configure at index time, not query time, for performance.</li>
          <li><strong>Score normalization</strong> for hybrid: BM25 scores are unbounded, cosine ∈ [-1,1]. Use RRF (rank-based, not score-based) to fuse — avoids the normalization headache.</li>
          <li><strong>Highlights for citation</strong>: <code>highlight: {`{"fields": {"text": {}}}`}</code> returns the matched phrase; the answer step uses these as citation anchors.</li>
        </ul>
      </>
    ),
  },
];

export default function VectorlessElasticsearchPage() {
  return (
    <div style={{ padding: '24px', maxWidth: 1100, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Vectorless RAG with Elasticsearch</h1>
        <p style={{ color: '#666', marginTop: 8 }}>
          Index page — when to use vectorless retrieval, the Elasticsearch query patterns, recommended mapping, and operator gotchas. Stage-1 documentation; Stage-2 will wire a live query playground via <code>/api/v1/retrieve?strategy=vectorless</code>.
        </p>
      </header>

      <nav
        style={{
          marginBottom: 24,
          padding: 12,
          background: '#fafafa',
          border: '1px solid #ddd',
          borderRadius: 4,
        }}
      >
        <strong>On this page:</strong>
        <ol style={{ margin: '8px 0 0 0' }}>
          {TOPICS.map((t) => (
            <li key={t.id}>
              <a href={`#${t.id}`}>{t.title}</a>
            </li>
          ))}
        </ol>
      </nav>

      {TOPICS.map((t) => (
        <section
          key={t.id}
          id={t.id}
          style={{
            marginBottom: 32,
            padding: 16,
            border: '1px solid #ddd',
            borderRadius: 4,
          }}
        >
          <h2 style={{ marginTop: 0 }}>{t.title}</h2>
          {t.body}
        </section>
      ))}

      {/* §49 compose footer */}
      <section
        style={{
          padding: 16,
          border: '1px dashed #999',
          borderRadius: 4,
          background: '#f8f8f8',
          fontSize: '0.85rem',
          marginBottom: 32,
        }}
      >
        <strong>Composes with</strong> (per §49):
        <ul style={{ marginTop: 8 }}>
          <li>
            <Link href="/admin/rag/deep">RAG deep dive</Link> — vectorless is one
            of the three retrieval modes (alongside vector + hybrid).
          </li>
          <li>
            <Link href="/admin/data/deep">Data preprocessing</Link> — chunking
            strategy directly affects BM25 quality (overly-long chunks dilute
            term frequency).
          </li>
          <li>
            <Link href="/admin/knowledge-graph/deep">Knowledge graph</Link> —
            graph entities can index as Elasticsearch documents for relationship-aware
            BM25 retrieval.
          </li>
          <li>
            <Link href="/admin/policy">PolisAI policy</Link> — the{' '}
            <code>retrieve:vectorless</code> scope gates which actors may use
            this retrieval mode.
          </li>
          <li>
            <Link href="/admin/paperclip">Paperclip</Link> — apply-rate
            histograms persist in the same Elasticsearch cluster (alongside
            audit logs via Filebeat).
          </li>
        </ul>
        <div style={{ marginTop: 8, color: '#666' }}>
          The Stage-1 RetrievalService contract supports{' '}
          <code>strategy=vectorless</code>; the query playground at{' '}
          <code>/api/v1/retrieve</code> is the Stage-2 surface that exercises it.
        </div>
      </section>
    </div>
  );
}
