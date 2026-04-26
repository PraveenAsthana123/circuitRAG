'use client';

/**
 * PageDownloadBar — auto-mounting download toolbar.
 *
 * Reads the page title from the first <h1 class="section-title"> on the
 * document, then renders DownloadBar with that title. Mounts as a sticky
 * pill in the top-right of the content area so it's always reachable
 * without dropping a download bar into every page.tsx.
 *
 * Skips render when no section-title is found (off-deep-dive pages).
 */

import { useEffect, useState } from 'react';
import DownloadBar from './DownloadBar';

export default function PageDownloadBar({ contentSelector = 'main' }: { contentSelector?: string }) {
  const [title, setTitle] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Wait one tick after mount so the page header has rendered.
    const t = setTimeout(() => {
      const h = document.querySelector('h1.section-title') as HTMLElement | null;
      if (h && h.textContent) setTitle(h.textContent.trim());
    }, 50);
    return () => clearTimeout(t);
  }, []);

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
        }}
      >
        <DownloadBar title={title} contentSelector={contentSelector} />
      </div>
    </div>
  );
}
