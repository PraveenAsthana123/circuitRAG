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
    const t = setTimeout(() => {
      // Prefer the explicit section title; fall back to first h1.
      const h =
        (document.querySelector('h1.section-title') as HTMLElement | null) ||
        (document.querySelector('h1') as HTMLElement | null) ||
        (document.querySelector('h2') as HTMLElement | null);
      if (h && h.textContent) setTitle(h.textContent.trim());
      // Capture content text for the SpeechReader.
      const main =
        (document.querySelector(contentSelector) as HTMLElement | null) ||
        (document.querySelector('article') as HTMLElement | null) ||
        document.body;
      if (main) {
        // Trim long pages to ~6000 chars; SpeechSynthesis chokes on huge
        // utterances in some browsers.
        const txt = (main.textContent || '').replace(/\s+/g, ' ').trim();
        setPageText(txt.slice(0, 6000));
      }
    }, 80);
    return () => clearTimeout(t);
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
