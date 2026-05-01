'use client';

/**
 * §26 Mounts the ErrorTracker once in dev mode and exposes it as
 * `window.__errors`. Sibling to <ClientErrorReporter /> — the reporter
 * POSTs errors to the backend; this tracker keeps a local F12-readable
 * buffer for the developer.
 *
 * No-op in production: the runtime cost of console wrapping +
 * PerformanceObservers is fine for dev but we don't ship it to users.
 */

import { useEffect } from 'react';
import { errorTracker } from '../utils/errorTracker';

export default function ErrorTrackerInit() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (process.env.NODE_ENV !== 'development') return;
    if (window.__documindErrorTrackerInstalled) return;
    window.__documindErrorTrackerInstalled = true;
    errorTracker.init();
    window.__errors = errorTracker;
  }, []);
  return null;
}
