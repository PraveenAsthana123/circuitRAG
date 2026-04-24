import { useEffect, useState } from 'react';
import { api } from '../services/api';

export default function DocumentsPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listDocuments({ limit: 100 });
      setItems(res?.items || []);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.listDocuments({ limit: 100 });
        if (!cancelled) setItems(res?.items || []);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <>
      <h1 className="section-title">Documents</h1>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <strong>{items.length} documents</strong>
          <button className="btn" onClick={load}>Refresh</button>
        </div>
        {loading && <div className="list-empty">Loading...</div>}
        {!loading && items.length === 0 && (
          <div className="list-empty">No documents uploaded yet.</div>
        )}
        {!loading && items.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
                <th style={{ padding: 8 }}>Filename</th>
                <th style={{ padding: 8 }}>State</th>
                <th style={{ padding: 8 }}>Pages</th>
                <th style={{ padding: 8 }}>Chunks</th>
                <th style={{ padding: 8 }}>Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: 8 }}>{d.filename}</td>
                  <td style={{ padding: 8 }}>
                    <span className={`badge badge-${d.state}`}>{d.state}</span>
                  </td>
                  <td style={{ padding: 8 }}>{d.page_count ?? '—'}</td>
                  <td style={{ padding: 8 }}>{d.chunk_count ?? '—'}</td>
                  <td style={{ padding: 8, color: 'var(--text-muted)' }}>
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
