'use client';

import { Component, ReactNode } from 'react';
import { api } from '../lib/api';

interface State {
  error: Error | null;
}

/**
 * Top-level error boundary for client-side React errors. Next.js also has
 * app/error.tsx for route-level boundaries; this one catches render errors
 * below an individual page.
 */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught', error);
    api.reportClientError({
      kind: 'react_boundary',
      message: error.message || 'react boundary error',
      stack: error.stack ?? null,
      route: typeof window !== 'undefined' ? window.location.pathname : null,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
    }).catch(() => undefined);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card" style={{ marginTop: 24 }}>
          <h2>Something went wrong.</h2>
          <p className="field-help" style={{ marginTop: 8 }}>
            A client-side rendering error was caught before it could crash the whole app.
          </p>
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{String(this.state.error)}</pre>
          <button
            className="btn btn-primary"
            style={{ marginTop: 12 }}
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
