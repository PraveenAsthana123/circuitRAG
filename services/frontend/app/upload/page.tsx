'use client';

import { useMemo, useRef, useState } from 'react';
import { api, ApiError, type UploadResponse } from '@/lib/api';

export default function UploadPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sync, setSync] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState('');
  const [selectedFileType, setSelectedFileType] = useState('');
  const [selectedFileBytes, setSelectedFileBytes] = useState(0);
  const hasSelectedFile = selectedFileBytes > 0 || selectedFileName !== '';
  const selectedFileSize = useMemo(() => {
    if (!selectedFileBytes) return null;
    if (selectedFileBytes < 1024 * 1024) return `${Math.round(selectedFileBytes / 1024)} KB`;
    return `${(selectedFileBytes / (1024 * 1024)).toFixed(1)} MB`;
  }, [selectedFileBytes]);

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setResult(null);
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError('Pick a file first.');
      return;
    }
    setBusy(true);
    try {
      const res = await api.uploadDocument(file, { sync });
      setResult(res);
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
          <h1 className="section-title">Upload document</h1>
          <p className="page-subtitle">
            Add source files to the corpus and optionally wait for indexing inline for demo or
            validation flows.
          </p>
        </div>
      </div>

      <div className="card">
        {error && <div className="error">{error}</div>}
        {result && (
          <div className="surface-muted" style={{ marginBottom: 16 }}>
            <div>Document: <code>{result.document_id}</code></div>
            <div>State: <span className={`badge badge-${result.state}`}>{result.state}</span></div>
            <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>{result.message}</div>
          </div>
        )}
        <form onSubmit={handleUpload} className="form-stack">
          <div className="field-group">
            <label className="field-label" htmlFor="upload-file">Choose file</label>
            <input
              id="upload-file"
            type="file"
            ref={fileRef}
            accept=".pdf,.docx,.txt,.md,.html"
            className="input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              setSelectedFileName(file?.name ?? '');
              setSelectedFileType(file?.type ?? '');
              setSelectedFileBytes(file?.size ?? 0);
            }}
          />
          <div className="field-help">Supported: PDF, DOCX, TXT, Markdown, HTML. Max 50 MB.</div>
        </div>

          {hasSelectedFile && (
            <div className="surface-muted">
              <strong>Selected file</strong>
              <div style={{ marginTop: 8 }}>{selectedFileName}</div>
              <div className="result-meta">{selectedFileType || 'unknown type'} · {selectedFileSize}</div>
            </div>
          )}

          <label className="field-help">
            <input type="checkbox" checked={sync} onChange={(e) => setSync(e.target.checked)} />{' '}
            Run inline and wait until indexing completes
          </label>

          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? (
              <>
                <span className="spinner" /> Uploading...
              </>
            ) : (
              'Upload'
            )}
          </button>
        </form>
      </div>

      <div className="metrics-strip" style={{ marginTop: 24 }}>
        <div className="metric-card">
          <div className="metric-label">Async upload</div>
          <div className="metric-value">Fast</div>
          <div className="field-help">Returns quickly and lets workers finish the pipeline.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Sync upload</div>
          <div className="metric-value">Blocking</div>
          <div className="field-help">Useful for demos when you want the document ready immediately.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Accepted types</div>
          <div className="metric-value">5</div>
          <div className="field-help">PDF, DOCX, TXT, MD, HTML.</div>
        </div>
      </div>
    </>
  );
}
