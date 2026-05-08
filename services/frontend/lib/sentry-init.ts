/**
 * Sentry Stage-1 adapter — offline-safe browser RUM init.
 *
 * Matches the Langfuse / Rebuff pattern: opt-in via env var, lazy
 * SDK import, no-op when DSN unset. The existing
 * `ClientErrorReporter.tsx` stays — Sentry is defense-in-depth, not
 * a replacement. Existing component captures errors and POSTs to
 * /api/v1/admin/client-errors (dev-time backend visibility); Sentry
 * adds production-grade RUM + Web Vitals + release tracking + source
 * map symbolication.
 *
 * OFFLINE-SAFE:
 *   - When NEXT_PUBLIC_SENTRY_DSN is unset → init() returns immediately.
 *     No SDK import. No network. No console noise.
 *   - When @sentry/nextjs is not installed → init() catches ImportError
 *     and logs once at warning level. Caller path is never broken.
 *
 * OPERATOR OPT-IN (mandatory before Sentry actually reports):
 *   1. cd services/frontend && npm install --save @sentry/nextjs
 *   2. Generate a Sentry DSN at sentry.io (or self-hosted)
 *   3. Set NEXT_PUBLIC_SENTRY_DSN in services/frontend/.env.local
 *      (and the deployment env)
 *   4. Optional: SENTRY_ORG / SENTRY_PROJECT / SENTRY_AUTH_TOKEN
 *      for source map uploads at build time (server-side env, never
 *      NEXT_PUBLIC_*).
 *
 * COMPOSES WITH:
 *   - components/ClientErrorReporter.tsx (sibling — dev-time backend
 *     reporter; runs in parallel with Sentry, both intentional)
 *   - app/error.tsx + app/global-error.tsx (Next.js error boundaries)
 *   - mcp/tests/drill_sentry_stage1.py (locks this contract)
 *
 * Per CLAUDE.md §47.6 (observability is first-class), §48
 * (explainability — front-end errors land in audit trail), §51
 * forensic substrate, §57.1 production-grade-by-default (offline-safe
 * + lazy import + env-gated + no DSN leakage in client bundle).
 */

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN ?? '';
const ENVIRONMENT = process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? 'development';
const TRACES_SAMPLE_RATE = parseFloat(
  process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? '0.1',
);

let _initialized = false;

export function isAvailable(): boolean {
  return DSN.length > 0;
}

export function status(): {
  stage: number;
  enabled_env: boolean;
  available: boolean;
  environment: string;
  traces_sample_rate: number;
  initialized: boolean;
  fail_mode: 'OPEN';
  offline_safe: boolean;
  purpose: string;
} {
  return {
    stage: 1,
    enabled_env: DSN.length > 0,
    available: isAvailable(),
    environment: ENVIRONMENT,
    traces_sample_rate: TRACES_SAMPLE_RATE,
    initialized: _initialized,
    fail_mode: 'OPEN',
    offline_safe: true,
    purpose:
      'Browser RUM + Web Vitals + release tracking + source map ' +
      'symbolication. Offline-safe: NO-OP when NEXT_PUBLIC_SENTRY_DSN ' +
      'unset OR @sentry/nextjs not installed. Composes with the ' +
      'existing ClientErrorReporter (dev-time backend visibility) ' +
      '— both run in parallel; Sentry is defense-in-depth, not a ' +
      'replacement.',
  };
}

/**
 * Initialize Sentry RUM. Safe to call from a Client Component's
 * useEffect on mount. Idempotent: subsequent calls are no-ops.
 *
 * Fail-OPEN per §47.6: any init error is caught + logged once;
 * the page never breaks because Sentry isn't reachable.
 */
export async function init(): Promise<void> {
  if (_initialized) return;
  if (!isAvailable()) return; // No DSN → no-op
  _initialized = true; // Set BEFORE the import so retry doesn't double-init

  try {
    // Lazy dynamic import — pays the SDK cost only when DSN is set.
    // Drill step 5 enforces this (no static `import Sentry from
    // '@sentry/nextjs'` at module top).
    const Sentry = await import('@sentry/nextjs');
    Sentry.init({
      dsn: DSN,
      environment: ENVIRONMENT,
      tracesSampleRate: TRACES_SAMPLE_RATE,
      // Privacy: don't capture local URLs / IPs by default.
      sendDefaultPii: false,
    });
  } catch (err) {
    // Fail-OPEN — never break the page on observability init failure.
    // Reset _initialized so a future retry path can try again.
    _initialized = false;
    if (typeof console !== 'undefined') {
      console.warn(
        '[sentry-init] failed to initialize; running without Sentry:',
        err instanceof Error ? err.message : String(err),
      );
    }
  }
}
