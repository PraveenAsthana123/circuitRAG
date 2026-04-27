'use client';

/**
 * PageDownloadBar — auto-mounting toolbar with download formats + read-aloud.
 *
 * Reads the page title from the first <h1 class="section-title"> on the
 * document (or falls back to <h1>) and renders:
 *   📄 PDF · 📝 Word · 🔤 Text · 🌐 HTML · 📊 PPT · 🔊 Read
 *
 * Mounts as a sticky pill in the top-right of the content area. Skips
 * render gracefully when no h1 is found (off-content pages).
 *
 * Mounted at the ROOT layout so every page in the app (admin, tools,
 * upload, documents, ask) has the toolbar without per-page wiring.
 */

import { useEffect, useState } from 'react';
import DownloadBar from './DownloadBar';
import SpeechReader from './SpeechReader';

export default function PageDownloadBar({ contentSelector = 'main' }: { contentSelector?: string }) {
  const [title, setTitle] = useState<string | null>(null);
  const [pageText, setPageText] = useState<string>('');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);

    const capture = () => {
      const h =
        (document.querySelector('h1.section-title') as HTMLElement | null) ||
        (document.querySelector('h1') as HTMLElement | null) ||
        (document.querySelector('h2') as HTMLElement | null);
      if (h && h.textContent) setTitle(h.textContent.trim());
      const main =
        (document.querySelector(contentSelector) as HTMLElement | null) ||
        (document.querySelector('article') as HTMLElement | null) ||
        document.body;
      if (main) {
        // Capture ONLY headings + paragraphs + list items + table cells +
        // figure captions. Skip buttons, selects, inputs, code blocks,
        // and anything tagged data-speech-skip. The user complaint
        // 'it is reading button — which is not required' was caused by
        // raw textContent including toolbar button labels. Limiting to
        // semantic content tags fixes that.
        const SEMANTIC = 'h1, h2, h3, h4, h5, h6, p, li, td, th, blockquote, figcaption, dt, dd';
        const SKIP = new Set(['BUTTON', 'SELECT', 'INPUT', 'TEXTAREA', 'OPTION', 'OPTGROUP', 'LABEL', 'CODE', 'PRE', 'SVG', 'NAV', 'ASIDE']);
        const parts: string[] = [];
        const seen = new WeakSet<Element>();
        main.querySelectorAll(SEMANTIC).forEach((el) => {
          if (seen.has(el)) return;
          // Skip if any ancestor is a control/nav OR carries data-speech-skip
          let p: Element | null = el;
          while (p && p !== main) {
            if (SKIP.has(p.tagName)) return;
            if ((p as HTMLElement).dataset?.speechSkip === '1') return;
            p = p.parentElement;
          }
          // Skip if a nested heading/paragraph already captured (avoid dup)
          el.querySelectorAll(SEMANTIC).forEach((nested) => seen.add(nested));
          const txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
          if (txt) parts.push(txt);
        });
        const joined = parts.join('. ').replace(/\.\s*\./g, '.').slice(0, 12000);
        setPageText(joined);
      }
    };

    // Initial capture after first paint.
    const t = setTimeout(capture, 80);
    // Re-capture as async/client content lands. MutationObserver fires
    // for every DOM mutation; debounce to one capture every 400ms while
    // the page is settling, then disconnect after 5s of quiet — by then
    // mermaid + topic cards + lazy hydration have all completed.
    let debounce: ReturnType<typeof setTimeout> | null = null;
    let lastMutation = Date.now();
    const observer = new MutationObserver(() => {
      lastMutation = Date.now();
      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(capture, 400);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    const disconnectTimer = setInterval(() => {
      if (Date.now() - lastMutation > 5000) {
        observer.disconnect();
        clearInterval(disconnectTimer);
      }
    }, 1000);

    return () => {
      clearTimeout(t);
      if (debounce) clearTimeout(debounce);
      observer.disconnect();
      clearInterval(disconnectTimer);
    };
  }, [contentSelector]);

  if (!mounted || !title) return null;

  return (
    <div
      style={{
        position: 'sticky',
        top: 12,
        zIndex: 30,
        display: 'flex',
        justifyContent: 'flex-end',
        marginBottom: 12,
        marginTop: -8,
      }}
    >
      <div
        style={{
          background: 'rgba(255,255,255,0.92)',
          backdropFilter: 'blur(4px)',
          padding: '6px 10px',
          borderRadius: 999,
          border: '1px solid #e5e7eb',
          boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <DownloadBar title={title} contentSelector={contentSelector} />
        {pageText && (
          <>
            <span style={{ width: 1, height: 22, background: '#e5e7eb' }} />
            <SpeechReader text={pageText} compact />
          </>
        )}
      </div>
    </div>
  );
}
