'use client';

import { useState } from 'react';
import { api, ApiError, type AskResponse } from '@/lib/api';

export default function AskPage() {
  const [query, setQuery] = useState('');
  const [strategy, setStrategy] = useState<'hybrid' | 'vector' | 'graph'>('hybrid');
  const [topK, setTopK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.ask(
        { query, strategy, top_k: topK },
        { debug: true },
      );
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="section-title">Ask</h1>
      <form className="card" onSubmit={submit}>
        <textarea
          className="textarea"
          placeholder="What does this document say about..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div style={{ display: 'flex', gap: 12, marginTop: 12, alignItems: 'center' }}>
          <label style={{ fontSize: 'var(--font-size-sm)' }}>
            Strategy{' '}
            <select
              className="select"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as 'hybrid' | 'vector' | 'graph')}
              style={{ width: 140, display: 'inline-block' }}
            >
              <option value="hybrid">hybrid</option>
              <option value="vector">vector only</option>
              <option value="graph">graph only</option>
            </select>
          </label>
          <label style={{ fontSize: 'var(--font-size-sm)' }}>
            top_k{' '}
            <input
              type="number"
              min={1}
              max={20}
              className="input"
              style={{ width: 70, display: 'inline-block' }}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </label>
          <span style={{ flex: 1 }} />
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

      {result && (
        <div className="card" style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <strong>Answer</strong>
            <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)' }}>
              confidence {Math.round(result.confidence * 100)}% · tokens {result.tokens_prompt}/
              {result.tokens_completion} · prompt {result.prompt_version}
            </span>
          </div>
          <div style={{ marginTop: 12, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
            {result.answer}
          </div>

          {result.citations?.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <strong>Citations</strong>
              {result.citations.map((c) => (
                <div className="citation" key={c.chunk_id}>
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
          )}

          {result.debug && (
            <details style={{ marginTop: 24, fontSize: 'var(--font-size-sm)' }}>
              <summary style={{ cursor: 'pointer' }}>Debug</summary>
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
      )}
    </>
  );
}
