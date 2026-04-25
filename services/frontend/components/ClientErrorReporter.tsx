'use client';

/**
 * Global client-side error reporter — wires window.onerror +
 * window.onunhandledrejection so uncaught JS exceptions and
 * unhandled Promise rejections POST to /api/v1/admin/client-errors.
 *
 * Mounted once at the root layout. Best-effort: a failed report
 * MUST NOT break further error handling, so we swallow the POST's
 * own errors.
 *
 * Closes the gap that bit during the techstack page rollout: the
 * user reported "Application error: client-side exception" but I
 * had no backend visibility into what JS error fired. With this in
 * place, the next browser-side error shows up in the admin
 * dashboard automatically.
 *
 * Privacy / security:
 *   * No DOM content captured. Just kind + message + stack +
 *     route + user-agent.
 *   * Stack traces capped server-side at 4KB.
 *   * The endpoint is dev-time only; production replaces this with
 *     a real RUM SDK (Sentry / Faro / Datadog) at the layout level.
 */

import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type ChunkRecoveryBanner = {
  route: string;
  at: number;
};

const CHUNK_RELOAD_COOLDOWN_MS = 5 * 60 * 1000;
const CHUNK_BANNER_TTL_MS = 30 * 1000;

// Keep the window-property names stable so a hot-reload doesn't
// register two listeners. The globals dance with `as any` is
// deliberate — we attach a marker to window without fighting types.
declare global {
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  interface Window {
    __documindClientErrorReporterInstalled?: boolean;
  }
}

export default function ClientErrorReporter() {
  const [chunkBanner, setChunkBanner] = useState<ChunkRecoveryBanner | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.__documindClientErrorReporterInstalled) return;
    window.__documindClientErrorReporterInstalled = true;

    function isChunkLoadError(message: string, stack?: string | null): boolean {
      const hay = `${message}\n${stack ?? ''}`;
      return /ChunkLoadError|Loading chunk \d+ failed|Failed to fetch dynamically imported module/i.test(hay);
    }

    function loadChunkBanner() {
      try {
        const raw = sessionStorage.getItem('documind_chunk_recovered_banner');
        if (!raw) return null;
        const parsed = JSON.parse(raw) as ChunkRecoveryBanner;
        if (!parsed?.route || typeof parsed.at !== 'number') {
          sessionStorage.removeItem('documind_chunk_recovered_banner');
          return null;
        }
        if (Date.now() - parsed.at > CHUNK_BANNER_TTL_MS) {
          sessionStorage.removeItem('documind_chunk_recovered_banner');
          return null;
        }
        sessionStorage.removeItem('documind_chunk_recovered_banner');
        return parsed;
      } catch {
        return null;
      }
    }

    const pendingBanner = loadChunkBanner();
    if (pendingBanner) {
      setChunkBanner(pendingBanner);
      window.setTimeout(() => setChunkBanner(null), 10000);
    }

    function maybeRecoverChunkError(message: string, stack?: string | null) {
      if (!isChunkLoadError(message, stack)) return;
      const route = window.location.pathname || '/';
      const key = `documind_chunk_reload_attempted:${route}`;
      try {
        const lastAttempt = Number(sessionStorage.getItem(key) ?? '0');
        if (Number.isFinite(lastAttempt) && Date.now() - lastAttempt < CHUNK_RELOAD_COOLDOWN_MS) {
          return;
        }
        sessionStorage.setItem(key, String(Date.now()));
        sessionStorage.setItem('documind_chunk_recovered_banner', JSON.stringify({
          route,
          at: Date.now(),
        } satisfies ChunkRecoveryBanner));
      } catch {
        // If sessionStorage is unavailable, fail open once.
      }
      // Give the best-effort telemetry POST a short head start before reload.
      window.setTimeout(() => window.location.reload(), 150);
    }

    function safeReport(body: Parameters<typeof api.reportClientError>[0]) {
      // Fire-and-forget. Catch the catch — a reporting failure
      // mustn't loop into another reporting attempt.
      api.reportClientError(body).catch(() => undefined);
    }

    function onError(ev: ErrorEvent) {
      const message = ev.message || 'unknown';
      const stack = ev.error?.stack ?? null;
      safeReport({
        kind: 'window_error',
        message,
        stack,
        route: window.location.pathname,
        user_agent: navigator.userAgent,
        extra: {
          filename: ev.filename ?? null,
          lineno: ev.lineno ?? null,
          colno: ev.colno ?? null,
        },
      });
      maybeRecoverChunkError(message, stack);
    }

    function onRejection(ev: PromiseRejectionEvent) {
      const reason = ev.reason;
      const message = (() => {
        if (reason instanceof Error) return reason.message;
        if (typeof reason === 'string') return reason;
        try {
          return JSON.stringify(reason);
        } catch {
          return String(reason);
        }
      })();
      const stack = reason instanceof Error ? reason.stack : null;
      safeReport({
        kind: 'unhandled_rejection',
        message: message || 'unhandled promise rejection',
        stack: stack ?? null,
        route: window.location.pathname,
        user_agent: navigator.userAgent,
      });
      maybeRecoverChunkError(message, stack);
    }

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      // No removeEventListener — the install-once guard above means
      // this effect runs at most once per mount. If the component
      // unmounts (rare; root component lifetime ≈ tab lifetime),
      // listeners stay attached. That's fine for an error reporter:
      // we want to capture errors AT all times, not only when the
      // component is mounted.
    };
  }, []);

  return chunkBanner ? (
    <div className="client-recovery-banner" role="status" aria-live="polite">
      <div>
        <strong>App updated.</strong> Recovered from a stale browser chunk on{' '}
        <code>{chunkBanner.route}</code>.
      </div>
      <button
        type="button"
        className="client-recovery-banner-dismiss"
        onClick={() => setChunkBanner(null)}
        aria-label="Dismiss app recovery banner"
      >
        Dismiss
      </button>
    </div>
  ) : null;
}
