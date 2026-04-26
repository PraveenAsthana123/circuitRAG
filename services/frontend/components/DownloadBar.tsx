'use client';

/**
 * DownloadBar — Print-to-PDF, Word, Text, HTML, PPT downloads for any page.
 *
 * Approach (one server-free path each):
 * - PDF:  window.print() — browser handles "Save as PDF" via print dialog.
 * - Word: emit HTML blob with .doc + application/msword MIME. Word opens.
 * - Text: extract textContent of the content region; download .txt.
 * - HTML: download raw .html for archival.
 * - PPT:  pptxgenjs library generates a real .pptx with title slide +
 *         section slides built from h1/h2/h3 + paragraph content.
 */

import { useState } from 'react';

type Props = {
  title: string;
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

function getContentEl(selector: string): HTMLElement | null {
  if (typeof document === 'undefined') return null;
  return document.querySelector(selector) as HTMLElement | null;
}

function getContentHTML(selector: string): string {
  const el = getContentEl(selector);
  if (!el) return document.body.innerHTML;
  return el.innerHTML;
}

function getContentText(selector: string): string {
  const el = getContentEl(selector);
  if (!el) return document.body.textContent || '';
  return el.textContent || '';
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

// Self-hosted pptxgenjs UMD bundle. Loaded once per session via script tag.
declare global {
  interface Window {
    PptxGenJS?: unknown;
    __pptxLoading?: Promise<unknown>;
  }
}
const PPTXGEN_URL = '/pptxgen.bundle.js';
function ensurePptxgen(): Promise<typeof window.PptxGenJS> {
  if (typeof window === 'undefined') return Promise.reject(new Error('ssr'));
  if (window.PptxGenJS) return Promise.resolve(window.PptxGenJS);
  if (window.__pptxLoading) return window.__pptxLoading.then(() => window.PptxGenJS);
  window.__pptxLoading = new Promise<unknown>((resolve, reject) => {
    const s = document.createElement('script');
    s.src = PPTXGEN_URL;
    s.async = true;
    s.onload = () => resolve(window.PptxGenJS);
    s.onerror = () => reject(new Error('pptxgen-load-failed'));
    document.head.appendChild(s);
  });
  return window.__pptxLoading.then(() => window.PptxGenJS);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Walk the content region and pull out section titles + their bullet text
// for PPT slides. h1/h2/h3 = slide title; subsequent <p>/<li> until next
// heading become bullets.
type Slide = { title: string; bullets: string[] };
function extractSlides(selector: string): Slide[] {
  const el = getContentEl(selector);
  if (!el) return [];
  const slides: Slide[] = [];
  let current: Slide | null = null;
  const walk = (node: Node) => {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = (node as HTMLElement).tagName;
    if (/^H[123]$/.test(tag)) {
      if (current) slides.push(current);
      current = { title: (node.textContent || '').trim().slice(0, 100), bullets: [] };
      return;
    }
    if (/^(P|LI)$/.test(tag) && current) {
      const t = (node.textContent || '').trim();
      if (t) current.bullets.push(t.slice(0, 200));
      return;
    }
    node.childNodes.forEach(walk);
  };
  el.childNodes.forEach(walk);
  if (current) slides.push(current);
  return slides.slice(0, 100); // cap at 100 slides
}

export default function DownloadBar({ title, contentSelector = 'main' }: Props) {
  const [busy, setBusy] = useState<'pdf' | 'word' | 'text' | 'html' | 'ppt' | null>(null);
  const fname = safeFilename(title);

  const onPdf = () => {
    setBusy('pdf');
    try { window.print(); } finally { setBusy(null); }
  };

  const onWord = () => {
    setBusy('word');
    try {
      const inner = getContentHTML(contentSelector);
      const html = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8" /><title>${escapeHtml(title)}</title>
<style>body{font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#000}h1,h2,h3{color:#1e3a8a}table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:4px 6px}pre{background:#f5f5f5;padding:8px}</style>
</head><body><h1>${escapeHtml(title)}</h1>${inner}</body></html>`;
      downloadBlob(`${fname}.doc`, new Blob([html], { type: 'application/msword' }));
    } finally { setBusy(null); }
  };

  const onText = () => {
    setBusy('text');
    try {
      const text = `${title}\n${'='.repeat(title.length)}\n\n${getContentText(contentSelector).replace(/\n{3,}/g, '\n\n').trim()}`;
      downloadBlob(`${fname}.txt`, new Blob([text], { type: 'text/plain;charset=utf-8' }));
    } finally { setBusy(null); }
  };

  const onHtml = () => {
    setBusy('html');
    try {
      const inner = getContentHTML(contentSelector);
      const html = `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${escapeHtml(title)}</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#000}h1,h2,h3{color:#1e3a8a}table{border-collapse:collapse}th,td{border:1px solid #ddd;padding:4px 6px}pre{background:#f5f5f5;padding:8px}</style>
</head><body><h1>${escapeHtml(title)}</h1>${inner}</body></html>`;
      downloadBlob(`${fname}.html`, new Blob([html], { type: 'text/html' }));
    } finally { setBusy(null); }
  };

  const onPpt = async () => {
    setBusy('ppt');
    try {
      // pptxgenjs imports node:fs/https which webpack can't bundle for
      // the client. Loaded from a script tag in /public — bypasses
      // webpack entirely.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const PptxGenJS: any = await ensurePptxgen();
      const pptx = new PptxGenJS();
      pptx.title = title;
      pptx.author = 'DocuMind';

      // Title slide
      const titleSlide = pptx.addSlide();
      titleSlide.background = { color: '1E3A8A' };
      titleSlide.addText(title, {
        x: 0.5, y: 2.5, w: 9, h: 1.5,
        fontSize: 36, color: 'FFFFFF', bold: true, align: 'center',
      });
      titleSlide.addText('DocuMind — auto-generated from page', {
        x: 0.5, y: 4.5, w: 9, h: 0.5,
        fontSize: 14, color: 'D1D5DB', align: 'center',
      });

      // Content slides from extracted sections
      const slides = extractSlides(contentSelector);
      for (const s of slides) {
        if (!s.title) continue;
        const slide = pptx.addSlide();
        slide.addText(s.title, {
          x: 0.5, y: 0.3, w: 9, h: 0.8,
          fontSize: 24, color: '1E3A8A', bold: true,
        });
        if (s.bullets.length > 0) {
          const bulletText = s.bullets.slice(0, 8).map((b) => ({ text: b, options: { bullet: true } }));
          slide.addText(bulletText, {
            x: 0.5, y: 1.2, w: 9, h: 5.8,
            fontSize: 14, color: '111827',
          });
        }
      }

      await pptx.writeFile({ fileName: `${fname}.pptx` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      <button type="button" onClick={onPdf} disabled={busy !== null} style={btnStyle('#991b1b')} title="Save as PDF">📄 PDF</button>
      <button type="button" onClick={onWord} disabled={busy !== null} style={btnStyle('#1e3a8a')} title="Download Word .doc">📝 Word</button>
      <button type="button" onClick={onText} disabled={busy !== null} style={btnStyle('#374151')} title="Download plain text">🔤 Text</button>
      <button type="button" onClick={onHtml} disabled={busy !== null} style={btnStyle('#16a34a')} title="Download HTML">🌐 HTML</button>
      <button type="button" onClick={onPpt} disabled={busy !== null} style={btnStyle('#b45309')} title="Download PowerPoint .pptx">📊 PPT{busy === 'ppt' ? '…' : ''}</button>
    </div>
  );
}
