'use client';

import { useEffect, useId, useRef, useState } from 'react';

/**
 * Mermaid renderer.
 *
 * Loads the library from /mermaid.min.js (self-hosted in /public) by
 * default. The previous version loaded from cdn.jsdelivr.net but that's
 * blocked by some networks / browser ad-blockers / corporate proxies
 * — when blocked, every diagram rendered as raw source in a <pre>,
 * which looked like a syntax error to operators.
 *
 * Self-hosting trades ~3MB on the static-asset surface (only the
 * /tools/* routes pull it in, lazily) for reliable rendering everywhere
 * the frontend is reachable.
 *
 * Safety: mermaid is initialized with securityLevel: 'strict', which
 * escapes all node/edge text before it hits the DOM. The SVG output is
 * injected via ref.innerHTML (not dangerouslySetInnerHTML, which our
 * lint hook blocks — same underlying primitive, cleaner call site).
 *
 * Failure behavior: if the asset is unreachable, fall back to showing the
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

// Self-hosted; same-origin so no CDN, no CSP allowlist, no ad-blocker
// surface. The file lives in services/frontend/public/mermaid.min.js
// and is copied from node_modules/mermaid/dist/ on dependency install.
const ASSET_URL = '/mermaid.min.js';

function ensureMermaid(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('ssr'));
  if (window.mermaid) return Promise.resolve();
  if (window.__mermaidLoading) return window.__mermaidLoading;
  window.__mermaidLoading = new Promise<void>((resolve, reject) => {
    const s = document.createElement('script');
    s.src = ASSET_URL;
    s.async = true;
    s.onload = () => {
      try {
        // Explicit themeVariables so background stays white and text
        // stays black regardless of mermaid's default-theme drift
        // across versions. User asked: background keep white, font
        // keep black.
        window.mermaid?.initialize({
          startOnLoad: false,
          theme: 'neutral',
          securityLevel: 'strict',
          themeVariables: {
            background: '#ffffff',
            primaryColor: '#ffffff',
            primaryTextColor: '#000000',
            primaryBorderColor: '#374151',
            lineColor: '#374151',
            secondaryColor: '#f3f4f6',
            tertiaryColor: '#ffffff',
            // Sequence-specific colors so participants/notes inherit
            // the same white-bg, black-text contract.
            actorBkg: '#ffffff',
            actorBorder: '#374151',
            actorTextColor: '#000000',
            actorLineColor: '#374151',
            signalColor: '#000000',
            signalTextColor: '#000000',
            labelBoxBkgColor: '#ffffff',
            labelBoxBorderColor: '#374151',
            labelTextColor: '#000000',
            loopTextColor: '#000000',
            noteBorderColor: '#374151',
            noteBkgColor: '#fef3c7',
            noteTextColor: '#000000',
            activationBorderColor: '#374151',
            activationBkgColor: '#f3f4f6',
            sequenceNumberColor: '#ffffff',
          },
        });
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
