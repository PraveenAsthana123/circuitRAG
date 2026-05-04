'use client';

/**
 * /admin/eval-harness — Layer 10 surface (Governance + Evaluation).
 *
 * Renders the 4 eval engines (Ragas / Guardrails AI / DeepEval / Snyk)
 * with Stage-1 scaffold status + Stage-2 wiring plan.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type EngineStatus = {
  name: string;
  available: boolean;
  required_dep: string;
  dep_pinned_in_requirements: boolean;
  layer: string;
  purpose: string;
};

type FileStatus = {
  path: string;
  present: boolean;
  bytes?: number;
};

type ApiPayload = {
  data: {
    stage: number;
    engines: EngineStatus[];
    all_stage1_scaffolds_ready: boolean;
    files: {
      eval_harness: FileStatus;
      eval_requirements: FileStatus;
      snyk_policy: FileStatus;
      snyk_workflow: FileStatus;
    };
    stage2_wiring_plan: string[];
  };
  correlation_id: string;
};

function statusBadge(ok: boolean, okLabel: string, badLabel: string) {
  return ok
    ? { bg: '#dff2dd', fg: '#1f8a4c', label: okLabel }
    : { bg: '#fef3e1', fg: '#c47a1a', label: badLabel };
}

export default function EvalHarnessPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/eval-harness', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setPayload((await r.json()) as ApiPayload);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const data = payload?.data;

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Eval Harness</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · scaffold · stub=true
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={refresh} disabled={loading}>
            {loading ? 'refreshing…' : 'refresh'}
          </button>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Layer 10 of the 11-layer architecture. Governance + evaluation
        scaffolds for RAG-quality (Ragas + DeepEval), output filtering
        (Guardrails AI, <strong>fail-OPEN</strong> in Stage-1 per §41.5),
        and security (Snyk). Stage-1 ships the import-safe contract;
        Stage-2 installs deps + wires real library calls.
      </p>

      {error && (
        <div
          style={{
            background: '#fdeaea',
            color: '#a4262c',
            padding: 12,
            border: '1px solid #a4262c',
            borderRadius: 4,
            marginBottom: 16,
          }}
        >
          <strong>Error:</strong> {error}
        </div>
      )}

      {data && (
        <>
          {/* Headline */}
          <section
            style={{
              padding: 16,
              border: '2px solid #ddd',
              borderRadius: 8,
              marginBottom: 16,
              background: '#fafafa',
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 16,
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Engines
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {data.engines.length}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Stage-1 scaffolds
              </div>
              <div>
                {(() => {
                  const b = statusBadge(
                    data.all_stage1_scaffolds_ready,
                    'all ready',
                    'incomplete',
                  );
                  return (
                    <span
                      style={{
                        background: b.bg,
                        color: b.fg,
                        padding: '4px 12px',
                        borderRadius: 3,
                        fontWeight: 600,
                        fontSize: '1.1rem',
                      }}
                    >
                      {b.label}
                    </span>
                  );
                })()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Stage-2 wiring steps
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {data.stage2_wiring_plan.length}
              </div>
            </div>
          </section>

          {/* Engines table */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Engines ({data.engines.length})</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Engine</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Layer</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Purpose</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Required dep</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Stage-1</th>
                </tr>
              </thead>
              <tbody>
                {data.engines.map((e) => {
                  const sb = statusBadge(
                    e.dep_pinned_in_requirements,
                    'scaffolded',
                    'missing',
                  );
                  return (
                    <tr key={e.name} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 6, fontWeight: 600 }}>{e.name}</td>
                      <td style={{ padding: 6, fontSize: '0.85rem' }}>{e.layer}</td>
                      <td style={{ padding: 6, fontSize: '0.85rem' }}>{e.purpose}</td>
                      <td style={{ padding: 6 }}><code>{e.required_dep}</code></td>
                      <td style={{ padding: 6 }}>
                        <span
                          style={{
                            background: sb.bg,
                            color: sb.fg,
                            padding: '2px 8px',
                            borderRadius: 3,
                            fontWeight: 600,
                          }}
                        >
                          {sb.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Files inventory */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Scaffold files</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>File</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Present</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Bytes</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.files).map(([key, f]) => {
                  const b = statusBadge(f.present, '✓ present', '✗ missing');
                  return (
                    <tr key={key} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 6 }}><code>{f.path}</code></td>
                      <td style={{ padding: 6 }}>
                        <span
                          style={{
                            background: b.bg,
                            color: b.fg,
                            padding: '2px 8px',
                            borderRadius: 3,
                          }}
                        >
                          {b.label}
                        </span>
                      </td>
                      <td style={{ padding: 6, textAlign: 'right' }}>
                        {f.bytes !== undefined ? f.bytes.toLocaleString() : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Stage-2 wiring plan */}
          <section
            style={{
              padding: 16,
              border: '1px solid #c47a1a',
              borderRadius: 4,
              background: '#fef3e1',
              marginBottom: 16,
              fontSize: '0.9rem',
            }}
          >
            <h3 style={{ marginTop: 0, color: '#c47a1a' }}>Stage-2 wiring plan</h3>
            <ol style={{ margin: 0 }}>
              {data.stage2_wiring_plan.map((step, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  {step}
                </li>
              ))}
            </ol>
            <div style={{ marginTop: 12, color: '#666', fontStyle: 'italic' }}>
              Each Stage-2 step lands as its own commit + drill update per §44
              autonomous-loop discipline. The drill_eval_governance_layer
              enforces stub=true on Stage-1; Stage-2 promotion explicitly
              flips that flag.
            </div>
          </section>

          {/* §49 compose footer */}
          <section
            style={{
              padding: 16,
              border: '1px dashed #999',
              borderRadius: 4,
              background: '#f8f8f8',
              fontSize: '0.85rem',
            }}
          >
            <strong>Composes with</strong> (per §49):
            <ul style={{ marginTop: 8 }}>
              <li>
                <Link href="/admin/policy">PolisAI policy</Link> — Guardrails
                AI output filter runs AFTER PolisAI gate, BEFORE the user sees
                the answer.
              </li>
              <li>
                <Link href="/admin/local-models">Local models</Link> — Ragas
                evaluates the council's RAG answers (faithfulness vs source
                chunks).
              </li>
              <li>
                <Link href="/admin/vectorless-elasticsearch">Vectorless RAG</Link>{' '}
                — Ragas context-precision scores the BM25 retrieval.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> — eval
                scores feed into the §48.4 audit row as quality signal.
              </li>
              <li>
                <Link href="/admin/checklist">Checklist</Link> — Snyk findings
                land here as new issues for the council to fix.
              </li>
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
