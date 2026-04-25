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

import { useEffect } from 'react';
import { api } from '../lib/api';

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
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.__documindClientErrorReporterInstalled) return;
    window.__documindClientErrorReporterInstalled = true;

    function safeReport(body: Parameters<typeof api.reportClientError>[0]) {
      // Fire-and-forget. Catch the catch — a reporting failure
      // mustn't loop into another reporting attempt.
      api.reportClientError(body).catch(() => undefined);
    }

    function onError(ev: ErrorEvent) {
      safeReport({
        kind: 'window_error',
        message: ev.message || 'unknown',
        stack: ev.error?.stack ?? null,
        route: window.location.pathname,
        user_agent: navigator.userAgent,
        extra: {
          filename: ev.filename ?? null,
          lineno: ev.lineno ?? null,
          colno: ev.colno ?? null,
        },
      });
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

  return null;
}
