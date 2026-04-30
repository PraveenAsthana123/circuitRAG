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

type BuildUpdateBanner = {
  currentBuildId: string;
  latestBuildId: string;
};

const CHUNK_RELOAD_COOLDOWN_MS = 5 * 60 * 1000;
const CHUNK_BANNER_TTL_MS = 30 * 1000;
const BUILD_POLL_INTERVAL_MS = 15 * 1000;

// Keep the window-property names stable so a hot-reload doesn't
// register two listeners. The globals dance with `as any` is
// deliberate — we attach a marker to window without fighting types.
declare global {
  interface Window {
    __documindClientErrorReporterInstalled?: boolean;
  }
}

export default function ClientErrorReporter() {
  const [chunkBanner, setChunkBanner] = useState<ChunkRecoveryBanner | null>(null);
  const [buildUpdateBanner, setBuildUpdateBanner] = useState<BuildUpdateBanner | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    let mounted = true;
    let pollTimer: number | null = null;
    const storageKey = 'documind_loaded_build_id';
    const dismissedKey = 'documind_dismissed_build_id';

    async function checkBuildUpdate() {
      const ctl = new AbortController();
      try {
        const info = await api.frontendBuildInfo(ctl.signal);
        const buildId = info.build_id;
        if (!mounted || !buildId) return;

        const currentBuildId = sessionStorage.getItem(storageKey);
        if (!currentBuildId) {
          sessionStorage.setItem(storageKey, buildId);
          return;
        }
        if (currentBuildId === buildId) return;

        const dismissedBuildId = sessionStorage.getItem(dismissedKey);
        if (dismissedBuildId === buildId) return;

        setBuildUpdateBanner({
          currentBuildId,
          latestBuildId: buildId,
        });
      } catch {
        // Build polling is best-effort only. Never surface as a user error.
      }
    }

    function schedulePoll() {
      if (pollTimer != null) window.clearInterval(pollTimer);
      pollTimer = window.setInterval(() => {
        if (document.visibilityState === 'visible') {
          void checkBuildUpdate();
        }
      }, BUILD_POLL_INTERVAL_MS);
    }

    function onVisibilityChange() {
      if (document.visibilityState === 'visible') {
        void checkBuildUpdate();
      }
    }

    void checkBuildUpdate();
    schedulePoll();
    window.addEventListener('focus', checkBuildUpdate);
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      mounted = false;
      if (pollTimer != null) window.clearInterval(pollTimer);
      window.removeEventListener('focus', checkBuildUpdate);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

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

    // Lazy disable: if the reporting endpoint ever returns a
    // non-recoverable status (404 / 405 / 501), suppress all subsequent
    // reports — both this session AND future navigations (sessionStorage)
    // — so a missing backend doesn't keep flooding the F12 console with
    // 404s on every page load.
    const REPORTER_DISABLED_KEY = 'documind_client_error_reporter_disabled';
    let endpointDisabled = false;
    try {
      if (window.sessionStorage.getItem(REPORTER_DISABLED_KEY) === '1') {
        endpointDisabled = true;
      }
    } catch {
      // sessionStorage unavailable; degrade to in-memory only.
    }

    function disableReporter() {
      endpointDisabled = true;
      try {
        window.sessionStorage.setItem(REPORTER_DISABLED_KEY, '1');
      } catch {
        // ignore
      }
    }

    // First-POST gate: if N parallel reports fire on the very first
    // page load (before sessionStorage flag is set), naive code POSTs
    // each one and the browser logs N × 404 console errors. Gate the
    // first POST on a singleton Promise; subsequent reports wait, then
    // suppress on 404/405/501.
    let firstReportPromise: Promise<void> | null = null;
    function safeReport(body: Parameters<typeof api.reportClientError>[0]) {
      if (endpointDisabled) return;
      if (firstReportPromise) {
        firstReportPromise.then(() => {
          if (endpointDisabled) return;
          api.reportClientError(body).catch(() => undefined);
        });
        return;
      }
      firstReportPromise = api.reportClientError(body).then(
        () => undefined,
        (err: unknown) => {
          const status = (err as { status?: number })?.status;
          if (status === 404 || status === 405 || status === 501) {
            disableReporter();
          }
        },
      );
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

    // ---- Network/API failure capture ---------------------------------
    // Wrap window.fetch so 4xx/5xx responses, network errors, timeouts,
    // and CORS failures get reported alongside JS exceptions. Runtime
    // errors were well-covered by onerror/unhandledrejection; HTTP-shaped
    // failures (like the localhost:3000/tools/rag-scenarios 500 the user
    // just hit) were invisible to the backend. Now they surface in
    // /admin/client-errors with the same correlation_id pivot.
    //
    // Hard rules:
    //   * Skip recursive reports — POSTs to the client-errors endpoint
    //     itself never report (otherwise a failing reporter loops).
    //   * 2xx and 3xx are silent. Only failures.
    //   * Skip /_next/* assets (chunk loads handled by ChunkLoadError
    //     path, not fetch). Skip /__nextjs_* dev probes.
    const originalFetch = window.fetch.bind(window);
    function wrappedFetch(
      input: RequestInfo | URL, init?: RequestInit,
    ): Promise<Response> {
      const url = typeof input === 'string'
        ? input
        : input instanceof URL ? input.toString() : input.url;
      const method = (init?.method || 'GET').toUpperCase();
      const isReportingEndpoint = url.includes('/api/v1/admin/client-errors');
      const isNextInternal = url.includes('/_next/')
        || url.includes('/__nextjs_');
      return originalFetch(input, init).then(
        (resp) => {
          if (!isReportingEndpoint && !isNextInternal && resp.status >= 400) {
            safeReport({
              kind: 'fetch_failed',
              message: `${method} ${url} → ${resp.status}`,
              route: window.location.pathname,
              user_agent: navigator.userAgent,
              correlation_id: resp.headers.get('X-Correlation-ID') ?? null,
              extra: {
                method,
                url,
                status: resp.status,
                status_text: resp.statusText,
              },
            });
          }
          return resp;
        },
        (err: unknown) => {
          // Network error / DNS / CORS / timeout (AbortError) all land here.
          // Skip our own reporting endpoint (avoid recursion) AND
          // AbortErrors when the caller deliberately cancelled (every
          // useEffect cleanup aborts in-flight requests; reporting
          // those is noise, not signal).
          const isAbort = (err as Error)?.name === 'AbortError';
          if (!isReportingEndpoint && !isNextInternal && !isAbort) {
            safeReport({
              kind: 'fetch_error',
              message: `${method} ${url} → ${(err as Error).message ?? String(err)}`,
              stack: (err as Error).stack ?? null,
              route: window.location.pathname,
              user_agent: navigator.userAgent,
              extra: {
                method,
                url,
                error_name: (err as Error).name ?? 'Error',
              },
            });
          }
          throw err; // never swallow — caller still sees the failure
        },
      );
    }
    // Mark on window so a hot-reload / re-mount doesn't double-wrap.
    if (!(window as unknown as { __documindFetchWrapped?: boolean }).__documindFetchWrapped) {
      window.fetch = wrappedFetch;
      (window as unknown as { __documindFetchWrapped?: boolean }).__documindFetchWrapped = true;
    }
    return () => {
      // No removeEventListener — the install-once guard above means
      // this effect runs at most once per mount. If the component
      // unmounts (rare; root component lifetime ≈ tab lifetime),
      // listeners stay attached. That's fine for an error reporter:
      // we want to capture errors AT all times, not only when the
      // component is mounted.
    };
  }, []);

  function refreshNow() {
    if (typeof window === 'undefined') return;
    const key = buildUpdateBanner?.latestBuildId;
    if (key) {
      sessionStorage.setItem('documind_loaded_build_id', key);
      sessionStorage.removeItem('documind_dismissed_build_id');
    }
    window.location.reload();
  }

  function dismissBuildUpdate() {
    if (typeof window === 'undefined') return;
    if (buildUpdateBanner?.latestBuildId) {
      sessionStorage.setItem('documind_dismissed_build_id', buildUpdateBanner.latestBuildId);
    }
    setBuildUpdateBanner(null);
  }

  if (buildUpdateBanner) {
    return (
      <div className="client-recovery-banner" role="status" aria-live="polite">
        <div>
          <strong>New frontend build detected.</strong> This tab is on{' '}
          <code>{buildUpdateBanner.currentBuildId}</code> and a newer build{' '}
          <code>{buildUpdateBanner.latestBuildId}</code> is available.
        </div>
        <div className="client-recovery-banner-actions">
          <button
            type="button"
            className="client-recovery-banner-primary"
            onClick={refreshNow}
          >
            Refresh now
          </button>
          <button
            type="button"
            className="client-recovery-banner-dismiss"
            onClick={dismissBuildUpdate}
            aria-label="Dismiss frontend update banner"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

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
