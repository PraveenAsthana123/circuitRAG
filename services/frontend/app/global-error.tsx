'use client';

import { useEffect } from 'react';
import { api } from '../lib/api';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    api.reportClientError({
      kind: 'global_error',
      message: error.message || 'global app error',
      stack: error.stack ?? null,
      route: typeof window !== 'undefined' ? window.location.pathname : null,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
      extra: {
        digest: error.digest ?? null,
      },
    }).catch(() => undefined);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <div style={{ minHeight: '100vh', padding: '32px', background: '#f8fafc', color: '#111827' }}>
          <div
            style={{
              maxWidth: 760,
              margin: '0 auto',
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 24,
              boxShadow: '0 10px 30px rgba(15, 23, 42, 0.08)',
            }}
          >
            <h1 style={{ fontSize: 28, marginBottom: 12 }}>Application error</h1>
            <p style={{ color: '#4b5563', marginBottom: 12 }}>
              A client-side exception occurred. The error was captured and sent to the admin
              client-error stream so it can be investigated without only relying on the browser
              console.
            </p>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                background: '#f9fafb',
                borderRadius: 8,
                padding: 12,
                fontSize: 13,
                marginBottom: 12,
              }}
            >
              {error.message}
              {error.digest ? `\n\ndigest: ${error.digest}` : ''}
            </pre>
            <button
              onClick={reset}
              style={{
                background: '#1d4ed8',
                color: '#fff',
                border: 0,
                borderRadius: 8,
                padding: '10px 14px',
                cursor: 'pointer',
                fontSize: 14,
              }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
