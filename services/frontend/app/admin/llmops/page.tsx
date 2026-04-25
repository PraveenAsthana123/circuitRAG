'use client';

/**
 * LLMOps coverage scorecard — the user's 14-category enterprise
 * LLMOps feature taxonomy mapped against THIS repo's current state.
 * Each row carries: status (shipped / partial / open), one-line
 * context, and (when shipped) a commit-hash anchor.
 *
 * Static content — the row-by-row status is hardcoded based on
 * known repo state at the time of this page's commit. Drifts on
 * its own; refresh on each meaningful LLMOps feature land. Not a
 * live registry — that's a separate, much bigger feature.
 *
 * Pattern matches /admin/python: catalog + filter + search + a
 * "where in this repo" column anchored to commits.
 */

import { useState } from 'react';

type Status = 'shipped' | 'partial' | 'open';

interface Item {
  name: string;
  status: Status;
  blurb: string;
  commit?: string;
}

interface Category {
  num: number;
  title: string;
  items: Item[];
}

const CATEGORIES: Category[] = [
  {
    num: 1,
    title: 'Data management',
    items: [
      { name: 'dataset registry', status: 'open', blurb: 'No dataset registry yet — datasets ingested ad hoc via ingestion-svc' },
      { name: 'dataset versioning', status: 'open', blurb: 'No version table; each ingest is a new corpus snapshot' },
      { name: 'raw vs cleaned dataset lineage', status: 'partial', blurb: 'Document state machine tracks ingest stages but not raw↔cleaned linkage' },
      { name: 'labeling and annotation tracking', status: 'open', blurb: 'No annotation surface' },
      { name: 'train/eval/test split management', status: 'open', blurb: 'evaluation-svc accepts datapoints inline; no persistent split registry' },
      { name: 'data quality profiling', status: 'open', blurb: 'No EDA-on-ingest profiling' },
      { name: 'data drift detection', status: 'open', blurb: 'No drift sentinel; could ride on existing metrics' },
      { name: 'PII and sensitive-data classification', status: 'partial', blurb: 'PIIScanner with 4 regex patterns — coarse, not Presidio-grade', commit: '09458ef' },
      { name: 'retention and deletion policy', status: 'open', blurb: 'ADR-017 planned; not implemented' },
      { name: 'source provenance tracking', status: 'partial', blurb: 'Documents store source filename + ingest time; no full lineage graph' },
    ],
  },
  {
    num: 2,
    title: 'Feature and retrieval data layer',
    items: [
      { name: 'feature store (offline)', status: 'open', blurb: 'No feature store; embeddings live in Qdrant directly' },
      { name: 'feature store (online)', status: 'open', blurb: 'No online feature serving' },
      { name: 'retrieval corpus registry', status: 'partial', blurb: 'Qdrant collections are the de-facto registry; not exposed as a typed surface' },
      { name: 'chunk versioning', status: 'open', blurb: 'Chunks are tied to document version, not independently versioned' },
      { name: 'embedding versioning', status: 'open', blurb: 'Embedding model is a config var; no version-bump audit' },
      { name: 'index versioning', status: 'open', blurb: 'No index-rebuild registry' },
      { name: 'prompt-context dataset versioning', status: 'open', blurb: 'No prompt-with-context version tracking' },
      { name: 'metadata schema management', status: 'partial', blurb: 'Metadata is per-chunk JSONB; no schema registry' },
    ],
  },
  {
    num: 3,
    title: 'Model management',
    items: [
      { name: 'model registry', status: 'partial', blurb: 'Models live per-prompt-row in governance.prompts.model column; no separate registry table', commit: 'a2418ad' },
      { name: 'model versioning', status: 'partial', blurb: 'Per-prompt model field carries the version string (e.g. "llama3.1:8b")' },
      { name: 'model card / metadata', status: 'open', blurb: 'No model_card surface yet' },
      { name: 'active vs inactive versions', status: 'partial', blurb: 'Indirectly via prompt status enum; no model-level lifecycle' },
      { name: 'promoted vs candidate models', status: 'open', blurb: 'No champion/challenger flow' },
      { name: 'rollback target tracking', status: 'open', blurb: 'No registry of "last good" model version' },
      { name: 'quantized vs full variants', status: 'open', blurb: 'Ollama variant info not surfaced' },
      { name: 'SLM vs LLM inventory', status: 'partial', blurb: '/admin/techstack lists installed Ollama clients but doesn\'t classify SLM/LLM', commit: 'b99059d' },
      { name: 'embedding model registry', status: 'open', blurb: 'Embedding model is env-config; no registry row' },
      { name: 'reranker model registry', status: 'open', blurb: 'No reranker wired' },
    ],
  },
  {
    num: 4,
    title: 'Prompt and policy management',
    items: [
      { name: 'prompt registry', status: 'shipped', blurb: 'governance.prompts table with name + version + template + status', commit: 'a2418ad' },
      { name: 'prompt versioning', status: 'shipped', blurb: 'Multiple versions per name supported (A/B rollout); drill verifies' },
      { name: 'active vs inactive prompts', status: 'shipped', blurb: 'Status enum {draft, active, archived, deprecated} enforced by CHECK', commit: 'a2418ad' },
      { name: 'prompt experiment history', status: 'open', blurb: 'No per-prompt-version eval-result join' },
      { name: 'policy/guardrail versioning', status: 'partial', blurb: 'GuardrailChecker config in code; no version registry', commit: 'ada94b9' },
      { name: 'system prompt governance', status: 'partial', blurb: 'Stored in governance.prompts; no separate role-aware lifecycle' },
      { name: 'template ownership', status: 'open', blurb: 'No owner field on prompts table' },
      { name: 'rollback support', status: 'partial', blurb: 'Set old version to active manually; no one-click rollback flow' },
    ],
  },
  {
    num: 5,
    title: 'Code and repo management',
    items: [
      { name: 'repo version tracking', status: 'partial', blurb: 'Git is the version system; no in-app build-hash surface yet' },
      { name: 'commit-to-model/prompt linkage', status: 'partial', blurb: 'Audit log carries actor + correlation; no commit metadata field' },
      { name: 'release tagging', status: 'open', blurb: 'No release registry; git tags only' },
      { name: 'branch/environment mapping', status: 'open', blurb: 'No env-to-branch table; deploys are direct' },
      { name: 'CI/CD quality gates', status: 'partial', blurb: 'Drill suite + regression-gate endpoint exist; no CI wiring yet', commit: '06153f3' },
      { name: 'infra-as-code versioning', status: 'open', blurb: 'docker-compose at repo root; not registered as IaC versioned artifact' },
      { name: 'migration version tracking', status: 'shipped', blurb: 'governance/migrations 001-008 with sequential numbers' },
      { name: 'evaluation code versioning', status: 'partial', blurb: 'Eval logic lives in evaluation-svc; tied to git commit' },
    ],
  },
  {
    num: 6,
    title: 'Experiment tracking',
    items: [
      { name: 'run tracking', status: 'open', blurb: 'No experiment_run table' },
      { name: 'parameter tracking', status: 'open', blurb: 'No params persisted per run' },
      { name: 'model/prompt config tracking', status: 'partial', blurb: 'Per-call audit row carries prompt_version; not as "experiment"' },
      { name: 'evaluation result tracking', status: 'partial', blurb: 'eval-svc /api/v1/evaluation/run returns metrics; not stored', commit: '06153f3' },
      { name: 'dataset-to-run linkage', status: 'open', blurb: 'No persistent linkage' },
      { name: 'cost tracking per run', status: 'partial', blurb: 'Token counter exists; not aggregated per run' },
      { name: 'latency tracking per run', status: 'partial', blurb: 'Per-tool latency histogram exists; not "per run"', commit: '598ca9a' },
      { name: 'comparison of runs', status: 'open', blurb: 'No two-run diff surface' },
      { name: 'champion vs challenger workflow', status: 'open', blurb: 'No A/B-with-decision flow' },
    ],
  },
  {
    num: 7,
    title: 'Deployment and serving',
    items: [
      { name: 'deployment registry', status: 'open', blurb: 'No deployments table' },
      { name: 'active deployment version', status: 'partial', blurb: '/health/upstreams shows running services; no version pinning', commit: '5f51ea2' },
      { name: 'canary deployment', status: 'open', blurb: 'No canary routing' },
      { name: 'blue/green deployment', status: 'open', blurb: 'No B/G config' },
      { name: 'shadow traffic', status: 'open', blurb: 'No shadow-route capability' },
      { name: 'routing by tenant/use case', status: 'partial', blurb: 'Tenant header propagated; no tenant-specific routing yet' },
      { name: 'fallback model routing', status: 'open', blurb: 'No primary→secondary model on breaker open' },
      { name: 'environment promotion', status: 'open', blurb: 'No env-promotion flow' },
      { name: 'serving config versioning', status: 'open', blurb: 'Config is env vars; no registry' },
    ],
  },
  {
    num: 8,
    title: 'Observability',
    items: [
      { name: 'prompt tracing', status: 'partial', blurb: 'OTel spans on RagInferenceService; no per-prompt-version filter yet' },
      { name: 'completion tracing', status: 'partial', blurb: 'OTel + token metric; richer answer-quality span on guardrails', commit: 'ada94b9' },
      { name: 'token usage tracking', status: 'shipped', blurb: 'documind_inference_tokens_total{model,kind} Prometheus counter', commit: '19ff1eb' },
      { name: 'latency tracking', status: 'shipped', blurb: 'Per-tool histogram + per-upstream probe', commit: '598ca9a' },
      { name: 'cost tracking', status: 'partial', blurb: 'Token counter is the proxy; no $-per-call aggregation' },
      { name: 'error tracking', status: 'shipped', blurb: 'Audit fail_closed counter + client-error reporter pipeline', commit: 'ebae1e3' },
      { name: 'output quality tracking', status: 'shipped', blurb: 'Guardrail span attributes (passed, confidence, violations)', commit: 'ada94b9' },
      { name: 'retrieval quality tracking', status: 'partial', blurb: 'Eval-svc has retrieval metrics; no per-call retrieval-quality span' },
      { name: 'feedback capture', status: 'open', blurb: 'No user-feedback ingestion path' },
      { name: 'correlation IDs across systems', status: 'shipped', blurb: 'X-Correlation-ID middleware threads through every log + audit + span', commit: '2064491' },
    ],
  },
  {
    num: 9,
    title: 'Evaluation and quality',
    items: [
      { name: 'offline evaluation', status: 'shipped', blurb: '/api/v1/evaluation/run computes metrics from datapoints', commit: '06153f3' },
      { name: 'online evaluation', status: 'partial', blurb: 'Per-call guardrail check is online; no aggregation surface' },
      { name: 'benchmark suites', status: 'open', blurb: 'No baseline file; perf-load doc planned' },
      { name: 'regression tests', status: 'shipped', blurb: '/api/v1/evaluation/regression-gate compares vs baseline', commit: '06153f3' },
      { name: 'hallucination checks', status: 'shipped', blurb: 'GuardrailChecker rejects hallucinated citations', commit: 'ada94b9' },
      { name: 'faithfulness checks', status: 'partial', blurb: 'Citation-grounding check; no semantic faithfulness scoring' },
      { name: 'relevance checks', status: 'partial', blurb: 'Retrieval scores feed confidence; no per-answer relevance gate' },
      { name: 'structured-output checks', status: 'open', blurb: 'No schema-validation guardrail' },
      { name: 'tool-action correctness checks', status: 'partial', blurb: 'Drafts + replay verify tool execution; no semantic correctness' },
      { name: 'safety evaluation', status: 'partial', blurb: 'PII patterns + guardrail rejection; no full safety taxonomy' },
    ],
  },
  {
    num: 10,
    title: 'Governance and lifecycle',
    items: [
      { name: 'model approval workflow', status: 'open', blurb: 'No approval queue' },
      { name: 'prompt approval workflow', status: 'partial', blurb: 'Status enum exists; no UI workflow on top' },
      { name: 'lifecycle states (draft/active/etc)', status: 'shipped', blurb: 'Prompts CHECK constraint enforces 4 states', commit: 'a2418ad' },
      { name: 'owner assignment', status: 'open', blurb: 'No owner field on registries' },
      { name: 'audit trail', status: 'shipped', blurb: 'governance.audit_log hash-chained per tenant + admin-trace lookup', commit: '2064491' },
      { name: 'compliance evidence', status: 'partial', blurb: 'Audit chain is the substrate; no compliance-report surface' },
      { name: 'risk classification', status: 'open', blurb: 'No risk score on actions' },
      { name: 'human review queue', status: 'partial', blurb: 'Drafts table is the HITL queue; resolve/reject endpoints', commit: '880022e' },
      { name: 'retirement and archival policy', status: 'open', blurb: 'ADR-017 planned' },
    ],
  },
  {
    num: 11,
    title: 'LLM vs SLM management',
    items: [
      { name: 'large-model serving inventory', status: 'partial', blurb: 'Ollama upstream probed; per-model serving info not surfaced' },
      { name: 'GPU resource tracking', status: 'open', blurb: 'No GPU/CPU metric per model' },
      { name: 'long-context config tracking', status: 'partial', blurb: 'max_tokens per prompt row in registry', commit: 'a2418ad' },
      { name: 'high-cost routing controls', status: 'open', blurb: 'No cost-aware router' },
      { name: 'small-model routing for cheap/fast paths', status: 'open', blurb: 'No SLM-vs-LLM routing layer' },
      { name: 'edge/local deployment options', status: 'open', blurb: 'Ollama is local; no remote-edge path' },
      { name: 'lightweight fallback registry', status: 'open', blurb: 'No fallback-model registry' },
      { name: 'task-specialized model inventory', status: 'open', blurb: 'No task→model mapping' },
    ],
  },
];

function statusBadgeClass(status: Status): string {
  if (status === 'shipped') return 'badge badge-active';
  if (status === 'partial') return 'badge badge-parsing';
  return 'badge badge-failed';
}

function statusLabel(status: Status): string {
  return status;
}

export default function LlmopsPage() {
  const [search, setSearch] = useState('');
  const [activeStatus, setActiveStatus] = useState<'all' | Status>('all');

  const totals = (() => {
    let shipped = 0, partial = 0, open = 0;
    for (const cat of CATEGORIES) {
      for (const item of cat.items) {
        if (item.status === 'shipped') shipped++;
        else if (item.status === 'partial') partial++;
        else open++;
      }
    }
    const total = shipped + partial + open;
    return { shipped, partial, open, total };
  })();

  const filteredCats = CATEGORIES.map((cat) => ({
    ...cat,
    items: cat.items.filter((item) => {
      if (activeStatus !== 'all' && item.status !== activeStatus) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          item.name.toLowerCase().includes(q)
          || item.blurb.toLowerCase().includes(q)
        );
      }
      return true;
    }),
  })).filter((cat) => cat.items.length > 0);

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">LLMOps coverage scorecard</h1>
          <p className="page-subtitle">
            14-category enterprise LLMOps feature taxonomy mapped
            against this repo's current state. Each row carries{' '}
            <span className="badge badge-active">shipped</span> /{' '}
            <span className="badge badge-parsing">partial</span> /{' '}
            <span className="badge badge-failed">open</span> with a
            commit-hash anchor when shipped. <strong>Static</strong> —
            updated when meaningful LLMOps features land.
          </p>
        </div>
      </div>

      <div className="metrics-strip">
        <div className="metric-card">
          <div className="metric-label">Shipped</div>
          <div className="metric-value">{totals.shipped}</div>
          <div className="field-help">end-to-end with drill</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Partial</div>
          <div className="metric-value">{totals.partial}</div>
          <div className="field-help">primitives present, surface incomplete</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Open</div>
          <div className="metric-value">{totals.open}</div>
          <div className="field-help">not started in this repo</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Total tracked</div>
          <div className="metric-value">{totals.total}</div>
          <div className="field-help">across 14 categories</div>
        </div>
      </div>

      {/* Filter / search controls. */}
      <div
        className="card"
        style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="field-help">Status</span>
          <select
            value={activeStatus}
            onChange={(e) => setActiveStatus(e.target.value as 'all' | Status)}
            style={{
              padding: '4px 8px',
              border: '1px solid #d1d5db',
              borderRadius: 4,
            }}
          >
            <option value="all">all</option>
            <option value="shipped">shipped</option>
            <option value="partial">partial</option>
            <option value="open">open</option>
          </select>
        </label>
        <input
          type="text"
          placeholder="search name / context"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search LLMOps capabilities"
          style={{
            flex: '1 1 240px',
            padding: '6px 10px',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            fontSize: 13,
          }}
        />
      </div>

      {filteredCats.length === 0 ? (
        <div className="card list-empty">No items match the current filter.</div>
      ) : (
        filteredCats.map((cat) => (
          <div key={cat.num} className="card">
            <div className="card-header" style={{ marginBottom: 12 }}>
              <strong>
                {cat.num}. {cat.title}
              </strong>{' '}
              <span className="field-help">
                ({cat.items.filter((i) => i.status === 'shipped').length}/
                {cat.items.length} shipped)
              </span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Capability</th>
                    <th>Status</th>
                    <th>Context</th>
                    <th>Commit</th>
                  </tr>
                </thead>
                <tbody>
                  {cat.items.map((item) => (
                    <tr key={`${cat.num}::${item.name}`}>
                      <td>
                        <code>{item.name}</code>
                      </td>
                      <td>
                        <span className={statusBadgeClass(item.status)}>
                          {statusLabel(item.status)}
                        </span>
                      </td>
                      <td>{item.blurb}</td>
                      <td>
                        {item.commit ? (
                          <code style={{ fontSize: 11 }}>{item.commit}</code>
                        ) : (
                          <span className="field-help">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))
      )}
    </>
  );
}
