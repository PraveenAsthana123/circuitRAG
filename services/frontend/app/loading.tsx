// Default loading UI for any route segment that suspends.

export default function Loading() {
  return (
    <div style={{ padding: 'var(--space-8)' }}>
      <span className="spinner" /> Loading...
    </div>
  );
}
