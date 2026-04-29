'use client';

import { useState } from 'react';
import { api, ApiError, type AskResponse } from '@/lib/api';
import AnswerAudioPanel from '@/components/AnswerAudioPanel';
import C4PageLinks from '@/components/C4PageLinks';
import SpeechReader from '@/components/SpeechReader';

type AskTurn = {
  id: string;
  query: string;
  result: AskResponse;
};

export default function AskPage() {
  const [query, setQuery] = useState('');
  const [strategy, setStrategy] = useState<'hybrid' | 'vector' | 'graph'>('hybrid');
  const [topK, setTopK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.ask(
        { query, strategy, top_k: topK },
        { debug: true },
      );
      const turn: AskTurn = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        query,
        result: res,
      };
      setTurns((prev) => [turn, ...prev].slice(0, 8));
      setQuery('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Ask</h1>
          <p className="page-subtitle">
            Query the indexed corpus with hybrid, vector-only, or graph-only retrieval and inspect
            the answer, citations, and debug metadata in one place.
          </p>
        </div>
      </div>

      <C4PageLinks
        title="Ask page — C4 view"
        summary="This surface is where the user-facing AI request enters the system. Use C4 to trace the request from actor and trust boundary, into deployable services, then down into retrieval, prompting, and runtime code."
        focus="Level 2 containers for request path, then Level 3 components for retrieval and answer generation."
        levels={['context', 'containers', 'components', 'observability']}
      />

      <form className="card form-stack" onSubmit={submit}>
        <div className="field-group">
          <label className="field-label" htmlFor="ask-query">Question</label>
          <textarea
            id="ask-query"
            className="textarea"
            placeholder="What does this document say about..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="field-help">
            Try: &quot;Summarize the contract renewal terms&quot; or &quot;What are the approval steps?&quot;
          </div>
        </div>

        <div className="form-row">
          <div className="field-group">
            <label className="field-label" htmlFor="ask-strategy">Retrieval strategy</label>
            <select
              id="ask-strategy"
              className="select"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as 'hybrid' | 'vector' | 'graph')}
            >
              <option value="hybrid">hybrid</option>
              <option value="vector">vector only</option>
              <option value="graph">graph only</option>
            </select>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="ask-topk">Top K</label>
            <input
              id="ask-topk"
              type="number"
              min={1}
              max={20}
              className="input"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </div>

          <div className="form-spacer" />
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? (
              <>
                <span className="spinner" /> Asking...
              </>
            ) : (
              'Ask'
            )}
          </button>
        </div>
      </form>

      {error && <div className="error" style={{ marginTop: 24 }}>{error}</div>}

      {turns.length > 0 && (
        <div style={{ marginTop: 24, display: 'grid', gap: 16 }}>
          {turns.map((turn) => {
            const result = turn.result;
            return (
              <div className="card" key={turn.id}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'flex-end',
                    marginBottom: 12,
                  }}
                >
                  <div
                    style={{
                      maxWidth: '80%',
                      background: '#dbeafe',
                      color: '#111827',
                      borderRadius: 14,
                      padding: '10px 12px',
                    }}
                  >
                    <div style={{ fontSize: 'var(--font-size-sm)', color: '#1e3a8a', marginBottom: 4 }}>
                      You
                    </div>
                    <div>{turn.query}</div>
                    <div style={{ marginTop: 8 }}>
                      <SpeechReader text={turn.query} compact />
                    </div>
                  </div>
                </div>

                <div className="result-header">
                  <div>
                    <strong>Assistant</strong>
                    <div className="result-meta">
                      correlation {result.correlation_id} · model {result.model}
                    </div>
                  </div>
                  <div className="result-meta">
                    confidence {Math.round(result.confidence * 100)}% · tokens {result.tokens_prompt}/
                    {result.tokens_completion} · prompt {result.prompt_version}
                  </div>
                </div>

                <div className="answer-body">{result.answer}</div>
                <AnswerAudioPanel text={result.answer} />

                <div className="split-grid">
                  <div className="stack">
                    {result.citations?.length > 0 && (
                      <div className="surface-muted">
                        <strong>Citations</strong>
                        <div style={{ marginTop: 12 }}>
                          {result.citations.map((c) => (
                            <div className="citation" key={`${turn.id}-${c.chunk_id}`}>
                              <div
                                style={{
                                  fontSize: 'var(--font-size-sm)',
                                  color: 'var(--text-muted)',
                                  marginBottom: 4,
                                }}
                              >
                                doc {c.document_id} · page {c.page_number}
                              </div>
                              <div>{c.snippet}...</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="stack">
                    <div className="surface-muted">
                      <strong>Run Summary</strong>
                      <div className="metrics-strip" style={{ marginTop: 12, marginBottom: 0 }}>
                        <div className="metric-card">
                          <div className="metric-label">Confidence</div>
                          <div className="metric-value">{Math.round(result.confidence * 100)}%</div>
                        </div>
                        <div className="metric-card">
                          <div className="metric-label">Prompt tokens</div>
                          <div className="metric-value">{result.tokens_prompt}</div>
                        </div>
                        <div className="metric-card">
                          <div className="metric-label">Completion tokens</div>
                          <div className="metric-value">{result.tokens_completion}</div>
                        </div>
                      </div>
                    </div>

                    {result.debug && (
                      <details className="surface-muted" style={{ fontSize: 'var(--font-size-sm)' }}>
                        <summary style={{ cursor: 'pointer', fontWeight: 'var(--font-weight-medium)' }}>
                          Debug payload
                        </summary>
                        <pre
                          style={{
                            whiteSpace: 'pre-wrap',
                            marginTop: 8,
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {JSON.stringify(result.debug, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
