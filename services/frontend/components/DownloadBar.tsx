'use client';

/**
 * DownloadBar — small toolbar with Print-to-PDF, Download Word, and
 * Download HTML buttons for any deep-dive page.
 *
 * Approach (zero-dependency, no backend):
 * - PDF:  window.print() — browser handles "Save as PDF" via the print
 *         dialog. Works in every modern browser. The printed output
 *         respects @print CSS rules.
 * - Word: emit a self-contained HTML blob with a .doc extension and
 *         the Microsoft Word MIME type. Word opens it; layout preserved;
 *         no external library needed (vs python-docx server-side).
 * - HTML: download the page's main content as raw .html for archival.
 *
 * For higher-fidelity PDF (no print dialog) the same UI swaps to a
 * server-side route /api/v1/export/pdf that runs headless Chrome —
 * future iteration. For PPT (.pptx) export we'd need a library like
 * pptxgenjs OR a server-side python-pptx pipeline — also future.
 */

import { useState } from 'react';

type Props = {
  /** Title used as the filename stem and in the Word document title */
  title: string;
  /** CSS selector for the page region to export. Defaults to `main` */
  contentSelector?: string;
};

function btnStyle(color: string): React.CSSProperties {
  return {
    padding: '4px 10px',
    background: '#fff',
    color,
    border: `1px solid ${color}`,
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
  };
}

function safeFilename(s: string): string {
  return s.replace(/[^\w\-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80) || 'export';
}

function getContentHTML(selector: string): string {
  if (typeof document === 'undefined') return '';
  const el = document.querySelector(selector);
  if (!el) return document.body.innerHTML;
  return el.innerHTML;
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function DownloadBar({ title, contentSelector = 'main' }: Props) {
  const [busy, setBusy] = useState<'pdf' | 'word' | 'html' | null>(null);
  const fname = safeFilename(title);

  const onPdf = () => {
    setBusy('pdf');
    try {
      window.print();
    } finally {
      setBusy(null);
    }
  };

  const onWord = () => {
    setBusy('word');
    try {
      const inner = getContentHTML(contentSelector);
      const html = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000; }
    h1, h2, h3 { color: #1e3a8a; }
    table { border-collapse: collapse; }
    table, th, td { border: 1px solid #ccc; padding: 4px 6px; }
    pre { background: #f5f5f5; padding: 8px; }
    /* Word will respect inline color; mermaid SVG renders as-is */
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  ${inner}
</body>
</html>`;
      const blob = new Blob([html], { type: 'application/msword' });
      downloadBlob(`${fname}.doc`, blob);
    } finally {
      setBusy(null);
    }
  };

  const onHtml = () => {
    setBusy('html');
    try {
      const inner = getContentHTML(contentSelector);
      const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" /><title>${escapeHtml(title)}</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#000}h1,h2,h3{color:#1e3a8a}table{border-collapse:collapse}th,td{border:1px solid #ddd;padding:4px 6px}pre{background:#f5f5f5;padding:8px}</style>
</head><body><h1>${escapeHtml(title)}</h1>${inner}</body></html>`;
      const blob = new Blob([html], { type: 'text/html' });
      downloadBlob(`${fname}.html`, blob);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      <button type="button" onClick={onPdf} disabled={busy !== null} style={btnStyle('#991b1b')} title="Save as PDF (browser print dialog)">
        📄 PDF
      </button>
      <button type="button" onClick={onWord} disabled={busy !== null} style={btnStyle('#1e3a8a')} title="Download as Word .doc">
        📝 Word
      </button>
      <button type="button" onClick={onHtml} disabled={busy !== null} style={btnStyle('#16a34a')} title="Download as HTML">
        🌐 HTML
      </button>
      <span
        title="PowerPoint export needs a server-side pipeline; coming next"
        style={{
          padding: '4px 10px',
          background: '#f3f4f6',
          color: '#9ca3af',
          border: '1px dashed #d1d5db',
          borderRadius: 6,
          fontSize: 13,
        }}
      >
        📊 PPT (soon)
      </span>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
