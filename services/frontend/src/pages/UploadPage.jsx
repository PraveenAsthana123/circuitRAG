import { useRef, useState } from 'react';
import { api } from '../services/api';

export default function UploadPage() {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [sync, setSync] = useState(false);

  async function handleUpload(e) {
    e.preventDefault();
    setError(null);
    setResult(null);
    const file = fileRef.current.files?.[0];
    if (!file) {
      setError('Pick a file first.');
      return;
    }
    setBusy(true);
    try {
      const res = await api.uploadDocument(file, { sync });
      setResult(res);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="section-title">Upload document</h1>
      <div className="card">
        {error && <div className="error">{error}</div>}
        {result && (
          <div style={{ marginBottom: 16 }}>
            <div>Document: <code>{result.document_id}</code></div>
            <div>State: <span className={`badge badge-${result.state}`}>{result.state}</span></div>
            <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>{result.message}</div>
          </div>
        )}
        <form onSubmit={handleUpload}>
          <input type="file" ref={fileRef} accept=".pdf,.docx,.txt,.md,.html" className="input" />
          <label style={{ display: 'block', marginTop: 12, fontSize: 'var(--font-size-sm)' }}>
            <input type="checkbox" checked={sync} onChange={(e) => setSync(e.target.checked)} /> Run inline (wait for indexing to complete)
          </label>
          <button type="submit" className="btn btn-primary" style={{ marginTop: 16 }} disabled={busy}>
            {busy ? <><span className="spinner" /> Uploading...</> : 'Upload'}
          </button>
        </form>
      </div>
      <div className="card" style={{ marginTop: 24, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
        <div>Supported: PDF, DOCX, TXT, Markdown, HTML. Max 50 MB.</div>
        <div>Sync mode blocks until indexing is complete — useful for demos.</div>
      </div>
    </>
  );
}
