'use client';

/**
 * /admin/kafka-events — Layer 8 surface (Kafka event-publisher).
 *
 * Stage-1 page: shows event-publisher status + topic catalog + the
 * "would-have-published" count (rows that landed in local audit logs;
 * once KAFKA_PUBLISH=1, they'd ALSO go to Kafka).
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type SchemaEntry = {
  source_layer: string;
  payload_shape: string;
  example_event_type: string;
};

type ApiPayload = {
  data: {
    stage: number;
    enabled: boolean;
    topics: Record<string, string>;
    bootstrap_servers: string;
    note: string;
    schema_per_topic: Record<string, SchemaEntry>;
    would_have_published: Record<string, number>;
    total_would_have_published: number;
  };
  correlation_id: string;
};

export default function KafkaEventsPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/kafka-events', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setPayload((await r.json()) as ApiPayload);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [autoRefresh, refresh]);

  const data = payload?.data;
  const enabledColor = data?.enabled
    ? { bg: '#dff2dd', fg: '#1f8a4c' }
    : { bg: '#fef3e1', fg: '#c47a1a' };

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Kafka Events</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · opt-in · fail-open
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={refresh} disabled={loading}>
            {loading ? 'refreshing…' : 'refresh'}
          </button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            auto-refresh 5s
          </label>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Layer 8 of the 11-layer architecture — Kafka event bus for new-layer
        audit events. Stage-1 is opt-in (KAFKA_PUBLISH=1 enables; default is
        no-op stub). Failure to publish never blocks the originating decision —
        local audit logs are the source of truth.
      </p>

      {error && (
        <div
          style={{
            background: '#fdeaea',
            color: '#a4262c',
            padding: 12,
            border: '1px solid #a4262c',
            borderRadius: 4,
            marginBottom: 16,
          }}
        >
          <strong>Error:</strong> {error}
        </div>
      )}

      {data && (
        <>
          {/* Status headline */}
          <section
            style={{
              padding: 16,
              border: '2px solid #ddd',
              borderRadius: 8,
              marginBottom: 16,
              background: '#fafafa',
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 16,
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                KAFKA_PUBLISH
              </div>
              <div>
                <span
                  style={{
                    background: enabledColor.bg,
                    color: enabledColor.fg,
                    padding: '4px 12px',
                    borderRadius: 3,
                    fontWeight: 600,
                    fontSize: '1.1rem',
                  }}
                >
                  {data.enabled ? 'enabled' : 'disabled (no-op)'}
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Topics
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {Object.keys(data.topics).length}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Would-have-published
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {data.total_would_have_published}
                <span style={{ fontSize: '0.85rem', color: '#666', marginLeft: 8 }}>
                  audit rows
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Bootstrap servers
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', wordBreak: 'break-all' }}>
                <code>{data.bootstrap_servers}</code>
              </div>
            </div>
          </section>

          {/* Topic catalog */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Topic catalog ({Object.keys(data.topics).length})</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Topic</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Source layer</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Event type</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Would-have-published</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.topics).map(([key, topic]) => {
                  const schema = data.schema_per_topic[topic];
                  const count = data.would_have_published[topic] || 0;
                  return (
                    <tr key={key} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 6 }}>
                        <code style={{ fontWeight: 600 }}>{topic}</code>
                      </td>
                      <td style={{ padding: 6 }}>{schema?.source_layer || '—'}</td>
                      <td style={{ padding: 6 }}>
                        <code>{schema?.example_event_type || '—'}</code>
                      </td>
                      <td style={{ padding: 6, textAlign: 'right', fontWeight: 600 }}>{count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Schema per topic */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>CloudEvents envelope (per §41.5)</h3>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                fontSize: '0.85rem',
                overflow: 'auto',
              }}
            >
              {`{
  "event_id":      "<UUID>",                    // unique per emission; stable on retry
  "event_type":    "<past-tense verb>",         // e.g. policy_decision_made
  "event_version": 1,                           // schema version; bump on incompatible change
  "source_layer":  "<layer name>",              // emitting layer (polisai / openclaw / ...)
  "timestamp_iso": "<ISO-8601 UTC>",            // emission time
  "correlation_id":"<UUID>",                    // cross-service trace
  "payload":       { ...domain-specific... }    // see schema_per_topic below
}`}
            </pre>
            <h4 style={{ marginTop: 16 }}>Per-topic payload shapes</h4>
            {Object.entries(data.schema_per_topic).map(([topic, schema]) => (
              <div key={topic} style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600 }}>
                  <code>{topic}</code>
                </div>
                <div style={{ color: '#666', fontSize: '0.85rem' }}>
                  Source: {schema.source_layer}
                </div>
                <pre
                  style={{
                    background: '#f5f5f5',
                    padding: 8,
                    fontSize: '0.8rem',
                    overflow: 'auto',
                    margin: '4px 0',
                  }}
                >
                  {schema.payload_shape}
                </pre>
              </div>
            ))}
          </section>

          {/* Operator note */}
          <section
            style={{
              padding: 16,
              border: '1px solid #c47a1a',
              borderRadius: 4,
              background: '#fef3e1',
              marginBottom: 16,
              fontSize: '0.9rem',
            }}
          >
            <strong>Operator note:</strong> {data.note}
          </section>

          {/* §49 compose footer */}
          <section
            style={{
              padding: 16,
              border: '1px dashed #999',
              borderRadius: 4,
              background: '#f8f8f8',
              fontSize: '0.85rem',
            }}
          >
            <strong>Composes with</strong> (per §49):
            <ul style={{ marginTop: 8 }}>
              <li>
                <Link href="/admin/policy">PolisAI policy</Link> — every
                allow/deny decision lands on{' '}
                <code>documind.policy.decisions</code>.
              </li>
              <li>
                <Link href="/admin/openclaw">OpenClaw</Link> — every dispatch
                attempt lands on <code>documind.openclaw.dispatches</code>.
              </li>
              <li>
                <Link href="/admin/agent-router">Agent Router</Link> — every
                classification lands on{' '}
                <code>documind.router.classifications</code>.
              </li>
              <li>
                <Link href="/admin/paperclip">Paperclip</Link> — sandbox-only;
                publishes via BFF (Stage-3) to preserve no-outbound contract.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> — the
                Kafka stream is the cross-service §48.4 audit trail.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-2 (production wiring): set KAFKA_PUBLISH=1, ensure
              docker-compose Kafka is up. Stage-3: subscribe consumers
              (observability dashboard, alerting, fraud monitoring).
            </div>
          </section>
        </>
      )}
    </div>
  );
}
