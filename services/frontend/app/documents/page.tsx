'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApiError, type DocumentSummary } from '@/lib/api';

export default function DocumentsPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <>
      <h1 className="section-title">Documents</h1>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <strong>{items.length} documents</strong>
          <button className="btn" onClick={() => load()}>Refresh</button>
        </div>
        {loading && <div className="list-empty">Loading...</div>}
        {!loading && items.length === 0 && <div className="list-empty">No documents uploaded yet.</div>}
        {!loading && items.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>State</th>
                <th>Pages</th>
                <th>Chunks</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id}>
                  <td>{d.filename}</td>
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
        )}
      </div>
    </>
  );
}
