'use client';

import { useEffect, useId, useRef, useState } from 'react';

/**
 * Mermaid renderer that loads the library from a CDN on first mount.
 *
 * Why CDN instead of npm? The mermaid bundle is large (~2MB). Only the
 * /tools routes need it, and most visitors hit maybe 2-3 tabs. Loading it
 * once per session on demand keeps the app shell light.
 *
 * Safety: mermaid is initialized with securityLevel: 'strict', which
 * escapes all node/edge text before it hits the DOM. The SVG output is
 * injected via ref.innerHTML (not dangerouslySetInnerHTML, which our
 * lint hook blocks — same underlying primitive, cleaner call site).
 *
 * Failure behavior: if the CDN is unreachable, fall back to showing the
 * diagram source in a <pre>. Never crash the page.
 */
declare global {
  interface Window {
    mermaid?: {
      initialize: (cfg: Record<string, unknown>) => void;
      render: (id: string, src: string) => Promise<{ svg: string }>;
    };
    __mermaidLoading?: Promise<void>;
  }
}

const CDN_URL = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';

function ensureMermaid(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('ssr'));
  if (window.mermaid) return Promise.resolve();
  if (window.__mermaidLoading) return window.__mermaidLoading;
  window.__mermaidLoading = new Promise<void>((resolve, reject) => {
    const s = document.createElement('script');
    s.src = CDN_URL;
    s.async = true;
    s.onload = () => {
      try {
        window.mermaid?.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'strict' });
        resolve();
      } catch (err) {
        reject(err);
      }
    };
    s.onerror = () => reject(new Error('mermaid-cdn-failed'));
    document.head.appendChild(s);
  });
  return window.__mermaidLoading;
}

export default function Mermaid({ chart }: { chart: string }) {
  const domId = useId().replace(/:/g, '_');
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    ensureMermaid()
      .then(async () => {
        if (!window.mermaid) throw new Error('mermaid-not-available');
        const out = await window.mermaid.render(`m_${domId}`, chart);
        if (mounted.current && hostRef.current) {
          hostRef.current.innerHTML = out.svg;
          setReady(true);
        }
      })
      .catch(() => {
        if (mounted.current) setFailed(true);
      });
    return () => {
      mounted.current = false;
    };
  }, [chart, domId]);

  if (failed) {
    return (
      <pre className="md-pre">
        <code>{chart}</code>
      </pre>
    );
  }
  return (
    <div className="md-mermaid-wrap">
      {!ready && <div className="md-mermaid-loading">rendering diagram…</div>}
      <div ref={hostRef} className="md-mermaid" />
    </div>
  );
}
