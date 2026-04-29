'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApiError, type DocumentSummary } from '@/lib/api';
import C4PageLinks from '@/components/C4PageLinks';
import SpeechReader from '@/components/SpeechReader';

export default function DocumentsPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [stateFilter, setStateFilter] = useState('all');

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listDocuments({ limit: 100 });
      setItems(res.items);
    } catch (err) {
      if (signal?.aborted) return;
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const filtered = items.filter((d) => {
    const matchesQuery =
      !query.trim() || d.filename.toLowerCase().includes(query.trim().toLowerCase());
    const matchesState = stateFilter === 'all' || d.state === stateFilter;
    return matchesQuery && matchesState;
  });

  const states = Array.from(new Set(items.map((item) => item.state))).sort();
  const activeCount = items.filter((item) => item.state === 'active').length;
  const failedCount = items.filter((item) => item.state === 'failed').length;

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Documents</h1>
          <p className="page-subtitle">
            Browse the indexed corpus, monitor document state, and quickly see whether ingestion is
            healthy or blocked.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => load()}>Refresh</button>
        </div>
      </div>

      <C4PageLinks
        title="Documents page — C4 view"
        summary="This page is the operational view of the corpus. The useful C4 lens is not only where the document service sits, but also how ingestion lifecycle, observability, and status transitions are exposed to operators."
        focus="Level 3 components for document state handling, plus Level 6 and 7 for observability and lifecycle."
        levels={['containers', 'components', 'observability', 'lifecycle']}
      />

      {error && <div className="error">{error}</div>}

      <div className="status-grid">
        <div className="status-card">
          <div className="status-card-title">Total documents</div>
          <div className="status-card-value">{items.length}</div>
        </div>
        <div className="status-card">
          <div className="status-card-title">Active</div>
          <div className="status-card-value">{activeCount}</div>
        </div>
        <div className="status-card">
          <div className="status-card-title">Failed</div>
          <div className="status-card-value">{failedCount}</div>
        </div>
        <div className="status-card">
          <div className="status-card-title">Visible rows</div>
          <div className="status-card-value">{filtered.length}</div>
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <div className="toolbar-group">
            <div className="field-group">
              <label className="field-label" htmlFor="document-search">Search filename</label>
              <input
                id="document-search"
                className="input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="policy.pdf"
              />
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="document-state">State</label>
              <select
                id="document-state"
                className="select"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
              >
                <option value="all">all states</option>
                {states.map((state) => (
                  <option key={state} value={state}>{state}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="result-meta">{filtered.length} of {items.length} documents shown</div>
        </div>

        {loading && <div className="list-empty">Loading...</div>}
        {!loading && items.length === 0 && <div className="list-empty">No documents uploaded yet.</div>}
        {!loading && items.length > 0 && filtered.length === 0 && (
          <div className="list-empty">No documents match the current filters.</div>
        )}
        {!loading && filtered.length > 0 && (
          <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Read</th>
                <th>State</th>
                <th>Pages</th>
                <th>Chunks</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id}>
                  <td>{d.filename}</td>
                  <td style={{ minWidth: 120 }}>
                    <SpeechReader
                      text={`Document ${d.filename}. State ${d.state}. Pages ${d.page_count ?? 'unknown'}. Chunks ${d.chunk_count ?? 'unknown'}. Created ${new Date(d.created_at).toLocaleString()}.`}
                      compact
                    />
                  </td>
                  <td>
                    <span className={`badge badge-${d.state}`}>{d.state}</span>
                  </td>
                  <td>{d.page_count ?? '-'}</td>
                  <td>{d.chunk_count ?? '-'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>
                    {new Date(d.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </>
  );
}
