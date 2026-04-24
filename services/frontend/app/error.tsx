'use client';

// Route-level error boundary (Next.js App Router convention).

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div style={{ padding: 'var(--space-8)' }}>
      <h2>Something went wrong.</h2>
      <pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{error.message}</pre>
      {error.digest ? <p style={{ color: 'var(--text-muted)' }}>digest: {error.digest}</p> : null}
      <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={reset}>
        Try again
      </button>
    </div>
  );
}
