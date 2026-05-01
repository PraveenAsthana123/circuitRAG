'use client';

/**
 * Pipelines hub — every pipeline in the RAG project surfaced in one view.
 *
 * Why this page exists:
 * - Operators need to see ALL active flows (ingest, retrieve, generate,
 *   eval, council, audit, drill, dispatcher, ...) at a glance — not
 *   discover them by reading 28 deep-dive pages.
 * - Each entry links to the deep-dive page (architecture detail) and to
 *   the runtime dashboard (when the pipeline has a live status surface).
 * - Composes with simulation-hub (live agent state) and local-models
 *   (live LLM state) so the operator's mental model = these three pages.
 */

import Link from 'next/link';

type Stage = { name: string; tool?: string };
type Pipeline = {
  id: string;
  emoji: string;
  name: string;
  purpose: string;
  trigger: string;
  status: 'shipped' | 'partial' | 'planned';
  stages: Stage[];
  composes_with: { href: string; label: string }[];
  drill?: string; // mcp/tests/drill_*.py path
  status_url?: string; // live BFF URL if any
};

const STATUS_COLORS: Record<Pipeline['status'], string> = {
  shipped: '#16a34a',
  partial: '#d97706',
  planned: '#6b7280',
};

const PIPELINES: Pipeline[] = [
  {
    id: 'ingestion',
    emoji: '📥',
    name: 'Document ingestion',
    purpose: 'Raw bytes → searchable chunks',
    trigger: 'Upload to /api/v1/documents/upload OR Kafka document_uploaded event',
    status: 'shipped',
    stages: [
      { name: 'Source detect', tool: 'mime + extension routing' },
      { name: 'Parser', tool: 'PDF / Word / HTML / CSV / JSON / XML' },
      { name: 'OCR (if image)', tool: 'planned: Tesseract' },
      { name: 'Preprocess + clean', tool: 'normalize, dedupe' },
      { name: 'Chunking', tool: 'documind_core.chunking (Strategy + Factory)' },
      { name: 'Metadata enrich', tool: 'tenant + source + version' },
      { name: 'PII scan', tool: 'documind_core.pii (Aho-Corasick + Luhn)' },
      { name: 'Quality score', tool: 'chunk-poisoning guard' },
      { name: 'Embedding', tool: 'Ollama nomic-embed-text + EmbeddingCache' },
      { name: 'Vector index', tool: 'Qdrant' },
      { name: 'Graph index', tool: 'Neo4j (entity-aware)' },
      { name: 'Audit row', tool: 'governance.audit_log (hash chain)' },
    ],
    composes_with: [
      { href: '/admin/data/deep', label: 'Data preprocessing deep dive' },
      { href: '/admin/rag/deep', label: 'RAG retrieval deep dive' },
    ],
    drill: 'mcp/tests/drill_ingestion_flow.py',
  },
  {
    id: 'retrieval',
    emoji: '🔎',
    name: 'Hybrid retrieval',
    purpose: 'Question → top-K context chunks',
    trigger: 'POST /api/v1/retrieve',
    status: 'shipped',
    stages: [
      { name: 'Auth + RBAC', tool: 'JWT + tenant scope' },
      { name: 'Query rewrite', tool: 'documind_core.query_rewriter' },
      { name: 'Embed query', tool: 'Ollama + EmbeddingCache' },
      { name: 'Vector search', tool: 'Qdrant via vector_searcher' },
      { name: 'BM25 search', tool: 'documind_core.bm25 (rank_bm25)' },
      { name: 'Graph search', tool: 'Neo4j via graph_searcher' },
      { name: 'RRF fusion', tool: 'documind_core.fusion.reciprocal_rank_fusion' },
      { name: 'Reranking', tool: 'cross-encoder (planned tighter)' },
      { name: 'MMR diversification', tool: 'documind_core.mmr' },
      { name: 'Audit + cache', tool: 'cache.py + audit.py' },
    ],
    composes_with: [
      { href: '/admin/rag/deep', label: 'RAG retrieval deep dive' },
      { href: '/admin/scaling-patterns/deep', label: 'Scaling patterns' },
    ],
    drill: 'mcp/tests/drill_hybrid_retrieval.py',
  },
  {
    id: 'generation',
    emoji: '🧠',
    name: 'LLM generation + grounding',
    purpose: 'Context → grounded answer with citations',
    trigger: 'POST /api/v1/answer (after retrieval)',
    status: 'shipped',
    stages: [
      { name: 'Prompt assembly', tool: 'token-budget pack via documind_core.tokens' },
      { name: 'Guardrails (input)', tool: 'ai_governance.PromptInjectionDetector' },
      { name: 'LLM call', tool: 'Ollama / vLLM (planned)' },
      { name: 'Guardrails (output)', tool: 'ai_governance.PIIScanner + AdversarialFilter' },
      { name: 'Citation linking', tool: 'documind_core.citations (claim → chunk)' },
      { name: 'Hallucination check', tool: 'CitationLinker.hallucination_rate' },
      { name: 'Audit row', tool: 'governance.audit_log + Langfuse' },
    ],
    composes_with: [
      { href: '/admin/explainability/deep', label: 'Explainability deep dive' },
      { href: '/admin/output-eval/deep', label: 'Output evaluation' },
    ],
    drill: 'mcp/tests/drill_generation_grounded.py',
  },
  {
    id: 'council',
    emoji: '🏛',
    name: 'Council pattern (3-model review)',
    purpose: 'Issue → 3 author proposals → reviewer + advisor → chair pick',
    trigger: 'scripts/run_council_batch.py OR /api/v1/council/run',
    status: 'shipped',
    stages: [
      { name: 'Author 1 (deepseek-coder:6.7b)', tool: 'Ollama' },
      { name: 'Author 2 (parallel)', tool: 'Ollama (asyncio.gather)' },
      { name: 'Author 3 (parallel)', tool: 'Ollama' },
      { name: 'Reviewer (codegemma:7b)', tool: 'cross-review of 3 proposals' },
      { name: 'Advisor (codellama:7b)', tool: 'synthesis + alternative' },
      { name: 'Chair (operator OR cloud-fallback)', tool: 'pick + apply' },
      { name: 'Audit row', tool: '.loop/issue_audit.jsonl + governance.audit_log' },
    ],
    composes_with: [
      { href: '/admin/agent-registry/deep', label: 'Agent registry (roles)' },
      { href: '/admin/local-models', label: 'Local models hub' },
    ],
    drill: 'mcp/tests/drill_council_pattern.py',
    status_url: '/api/v1/local-models',
  },
  {
    id: 'eval',
    emoji: '🧪',
    name: 'Evaluation pipeline',
    purpose: 'Golden set → run → score → regression report',
    trigger: 'scheduled cron OR /api/v1/eval/run',
    status: 'partial',
    stages: [
      { name: 'Load golden set', tool: 'tests/fixtures/golden/*.json' },
      { name: 'Run RAG against each Q', tool: 'evaluation-svc' },
      { name: 'Score groundedness', tool: 'documind_core.citations.hallucination_rate' },
      { name: 'Score retrieval relevance', tool: 'planned: Ragas integration' },
      { name: 'Score answer relevance', tool: 'planned: Ragas integration' },
      { name: 'Regression baseline', tool: 'compare to previous run' },
      { name: 'Report + alert', tool: 'Prometheus alert rules' },
    ],
    composes_with: [
      { href: '/admin/output-eval/deep', label: 'Output evaluation deep dive' },
      { href: '/admin/checklist/deep', label: 'Production checklist' },
    ],
    drill: 'mcp/tests/drill_eval_pipeline.py',
  },
  {
    id: 'audit',
    emoji: '🔐',
    name: 'Tamper-evident audit',
    purpose: 'Every sensitive event → hash-chained row in governance.audit_log',
    trigger: 'every state-changing call',
    status: 'shipped',
    stages: [
      { name: 'Event capture', tool: 'AuditWriter.write()' },
      { name: 'Look up previous hash', tool: 'per-tenant chain' },
      { name: 'Compute entry hash', tool: 'SHA-256 over canonical JSON' },
      { name: 'Persist row', tool: 'asyncpg → governance.audit_log' },
      { name: 'Verify chain (offline)', tool: 'scripts/audit_verify.py' },
    ],
    composes_with: [
      { href: '/admin/checklist/deep', label: 'Production checklist' },
      { href: '/admin/forensics', label: 'Forensics' },
    ],
    drill: 'mcp/tests/drill_audit_chain_integrity.py',
  },
  {
    id: 'drill',
    emoji: '🛡',
    name: 'Drill regression catalog',
    purpose: 'Every feature ships a drill; runner enforces no-regression',
    trigger: 'pre-commit OR scripts/run_drills.py OR CI',
    status: 'shipped',
    stages: [
      { name: 'Discover drills', tool: 'mcp/tests/drill_*.py glob' },
      { name: 'Parse RESOURCES tags', tool: 'parallel scheduling' },
      { name: 'Run in parallel', tool: 'asyncio.Condition + per-resource locks' },
      { name: 'Aggregate report', tool: 'JUnit XML + .loop/drill_status.json' },
      { name: 'Stop on first fail (optional)', tool: '--stop-on-fail flag' },
    ],
    composes_with: [
      { href: '/admin/post-release/deep', label: 'Post-release verification' },
    ],
    drill: 'self-locking — drill runner exercises every drill',
  },
  {
    id: 'issue-dispatcher',
    emoji: '🩹',
    name: 'Issue dispatcher (lint/type/sec auto-fix)',
    purpose: 'Deterministic discovery → routing → propose-or-apply',
    trigger: 'scripts/issue_scanner.py + dispatcher.py',
    status: 'shipped',
    stages: [
      { name: 'Scan (ruff)', tool: 'discovery is deterministic' },
      { name: 'Route per rule', tool: 'RULE_ROUTING dict' },
      { name: 'Auto-fix (ruff:autofix)', tool: 'safe + deterministic' },
      { name: 'Council review (medium)', tool: '3-model author + reviewer + advisor' },
      { name: 'Human-review (security)', tool: '§50.5 — never auto-apply S* rules' },
      { name: 'Audit row', tool: '.loop/issue_audit.jsonl' },
    ],
    composes_with: [
      { href: '/admin/code-quality/deep', label: 'Code quality deep dive' },
      { href: '/admin/local-models', label: 'Local models (council backend)' },
    ],
    drill: 'mcp/tests/drill_issue_dispatcher_format.py',
  },
  {
    id: 'breaker',
    emoji: '🚦',
    name: 'Circuit breaker / outbox',
    purpose: 'Dependency unhealthy → fast-fail; recovery → half-open probe',
    trigger: 'every external call wrapped in @breaker',
    status: 'shipped',
    stages: [
      { name: 'Call enters breaker', tool: 'breakers.py' },
      { name: 'Check state (closed/open/half-open)', tool: 'state machine' },
      { name: 'Reject fast (open)', tool: 'CircuitOpenError' },
      { name: 'Allow probe (half-open)', tool: 'limited rate' },
      { name: 'Outbox publish (success/fail)', tool: 'Kafka' },
      { name: 'Reset on consecutive successes', tool: 'half-open → closed' },
    ],
    composes_with: [
      { href: '/admin/breakers/deep', label: 'Breakers deep dive' },
    ],
    drill: 'mcp/tests/drill_breaker_transitions.py',
  },
  {
    id: 'load-test',
    emoji: '⚡',
    name: 'Load testing (5-phase k6)',
    purpose: 'Smoke → load → stress → soak → spike',
    trigger: 'scripts/load-test.sh',
    status: 'shipped',
    stages: [
      { name: 'Smoke (1-10 VU)', tool: 'k6 baseline.js' },
      { name: 'Load (target SLA)', tool: 'k6 baseline.js' },
      { name: 'Stress (0→2000 VU)', tool: 'find break point' },
      { name: 'Soak (24h)', tool: 'memory leak detection' },
      { name: 'Spike (0→peak in 60s)', tool: 'recovery <60s' },
      { name: 'Report → Prometheus', tool: '.loop/load-test/' },
    ],
    composes_with: [
      { href: '/admin/load-testing/deep', label: 'Load testing deep dive' },
    ],
    drill: 'mcp/tests/drill_load_test_setup.py',
  },
  {
    id: 'cdn-cache',
    emoji: '🌐',
    name: 'CDN cache + bypass',
    purpose: 'Static cached 7d at edge; API NEVER cached (idempotency safety)',
    trigger: 'every browser request through NGINX',
    status: 'shipped',
    stages: [
      { name: 'NGINX edge match', tool: 'proxy_cache_path keys_zone=static_cache' },
      { name: 'Static (Next _next/static)', tool: '7-day cache + immutable' },
      { name: 'API (proxy_no_cache 1)', tool: 'Cache-Control: no-store, private' },
      { name: 'Upload (cache_bypass)', tool: 'POST /api/v1/documents/upload' },
    ],
    composes_with: [
      { href: '/admin/api-gateway/deep', label: 'API gateway deep dive' },
    ],
    drill: 'mcp/tests/drill_cdn_cache_invariants.py',
  },
  {
    id: 'observability',
    emoji: '🔬',
    name: 'Observability (metrics + traces + logs + LLM ops)',
    purpose: 'Per-stage timing + cost + drift visible per correlation_id',
    trigger: 'every request',
    status: 'shipped',
    stages: [
      { name: 'OTel collector receives spans', tool: 'gRPC OTLP' },
      { name: 'Prometheus scrapes metrics', tool: 'documind_*_total counters' },
      { name: 'Jaeger renders traces', tool: 'per correlation_id' },
      { name: 'Grafana dashboards', tool: 'p95/p99/error/cost' },
      { name: 'Alertmanager fires alerts', tool: 'shared-webhook receiver' },
      { name: 'Langfuse LLM-ops', tool: 'opt-in profile' },
    ],
    composes_with: [
      { href: '/admin/llmops/deep', label: 'LLMOps deep dive' },
      { href: '/admin/forensics', label: 'Forensics' },
    ],
    drill: 'mcp/tests/drill_observability_stack_provisioning.py',
  },
];

function StatusPill({ status }: { status: Pipeline['status'] }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 12,
        fontSize: 11,
        fontWeight: 600,
        color: '#fff',
        backgroundColor: STATUS_COLORS[status],
        textTransform: 'uppercase',
        letterSpacing: 0.5,
      }}
    >
      {status}
    </span>
  );
}

function PipelineCard({ pipeline }: { pipeline: Pipeline }) {
  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 16,
        backgroundColor: '#ffffff',
        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 22 }}>{pipeline.emoji}</span>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#111827', flex: 1 }}>
          {pipeline.name}
        </h3>
        <StatusPill status={pipeline.status} />
      </div>
      <p style={{ margin: '4px 0 8px', fontSize: 13, color: '#374151' }}>{pipeline.purpose}</p>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: '#6b7280' }}>
        <strong>Trigger:</strong> <code>{pipeline.trigger}</code>
      </p>

      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
          Stages ({pipeline.stages.length})
        </div>
        <ol style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: '#4b5563', lineHeight: 1.6 }}>
          {pipeline.stages.map((s, i) => (
            <li key={i}>
              <strong>{s.name}</strong>
              {s.tool && (
                <span style={{ color: '#6b7280' }}> — <code style={{ fontSize: 11 }}>{s.tool}</code></span>
              )}
            </li>
          ))}
        </ol>
      </div>

      {pipeline.drill && (
        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>
          <strong>Drill:</strong> <code>{pipeline.drill}</code>
        </div>
      )}
      {pipeline.status_url && (
        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>
          <strong>Live BFF:</strong> <code>{pipeline.status_url}</code>
        </div>
      )}

      {pipeline.composes_with.length > 0 && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px dashed #e5e7eb' }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Composes with
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.5 }}>
            {pipeline.composes_with.map((c) => (
              <li key={c.href}>
                <Link href={c.href} style={{ color: '#2563eb', textDecoration: 'none' }}>
                  {c.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function PipelinesHub() {
  const counts = {
    total: PIPELINES.length,
    shipped: PIPELINES.filter((p) => p.status === 'shipped').length,
    partial: PIPELINES.filter((p) => p.status === 'partial').length,
    planned: PIPELINES.filter((p) => p.status === 'planned').length,
    stages: PIPELINES.reduce((sum, p) => sum + p.stages.length, 0),
  };

  return (
    <main
      style={{
        padding: 24,
        backgroundColor: '#f9fafb',
        minHeight: '100vh',
      }}
    >
      <header style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: '#111827' }}>
          🪢 Pipelines hub
        </h1>
        <p style={{ margin: '4px 0 12px', fontSize: 14, color: '#4b5563' }}>
          Every named flow in the RAG project surfaced in one node. Each card shows the
          purpose, trigger, ordered stages with the tool/library backing each, the drill
          that locks it, and the deep-dive pages it composes with.
        </p>
        <div style={{ display: 'flex', gap: 14, fontSize: 12, color: '#374151' }}>
          <span><strong>{counts.total}</strong> pipelines</span>
          <span style={{ color: STATUS_COLORS.shipped }}>● {counts.shipped} shipped</span>
          <span style={{ color: STATUS_COLORS.partial }}>● {counts.partial} partial</span>
          <span style={{ color: STATUS_COLORS.planned }}>● {counts.planned} planned</span>
          <span><strong>{counts.stages}</strong> stages total</span>
        </div>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))',
          gap: 16,
        }}
      >
        {PIPELINES.map((p) => (
          <PipelineCard key={p.id} pipeline={p} />
        ))}
      </div>

      <footer style={{ marginTop: 28, paddingTop: 16, borderTop: '1px solid #e5e7eb' }}>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          <strong>Composes with:</strong>{' '}
          <Link href="/admin/simulation" style={{ color: '#2563eb' }}>
            Simulation hub
          </Link>{' '}
          (live agent + tool state),{' '}
          <Link href="/admin/local-models" style={{ color: '#2563eb' }}>
            Local models
          </Link>{' '}
          (live LLM state),{' '}
          <Link href="/admin/checklist/deep" style={{ color: '#2563eb' }}>
            Production checklist
          </Link>{' '}
          (per-pipeline gate),{' '}
          <Link href="/admin/forensics" style={{ color: '#2563eb' }}>
            Forensics
          </Link>{' '}
          (correlation_id traversal across pipelines).
        </div>
      </footer>
    </main>
  );
}
