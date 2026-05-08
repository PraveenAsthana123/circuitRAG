'use client';

/**
 * SentryInit — mount-once Client Component that initializes the
 * Sentry SDK (when configured). Sibling to ClientErrorReporter
 * (defense in depth: ClientErrorReporter posts errors to the
 * dev-time backend; Sentry adds prod-grade RUM + Web Vitals).
 *
 * Mounts at the root layout. Safe to leave even when DSN unset —
 * sentry-init.init() returns immediately if NEXT_PUBLIC_SENTRY_DSN
 * is not provided (no SDK import, no network).
 *
 * Per CLAUDE.md §47.6 (observability), §51 forensic substrate,
 * §57.1 production-grade-by-default. Locked by
 * mcp/tests/drill_sentry_stage1.py.
 */

import { useEffect } from 'react';

export default function SentryInit() {
  useEffect(() => {
    // Lazy import the adapter — keeps SSR + RSC clean.
    void import('../lib/sentry-init').then((m) => {
      void m.init();
    });
  }, []);

  return null;
}
