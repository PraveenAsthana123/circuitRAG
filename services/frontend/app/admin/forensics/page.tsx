'use client';

/**
 * Forensics — operator-facing trace → draft → audit → HITL
 * reconstruction by correlation_id.
 *
 * Realises the documented forensics flow at:
 *   /admin/tracing/deep#trace-draft-audit-linkage
 *   /admin/explainability/deep#audit-rag-contract-regulation
 *
 * The operator pastes a correlation_id (from the dashboard / a user
 * complaint / an alert) plus a tenant_id, and gets the full
 * reasoning trail across:
 *  - governance.audit_log    (who did what, when, with what details)
 *  - governance.action_drafts (durable record of MCP tool actions
 *    that couldn't execute and need human triage)
 *  - governance.hitl_queue   (RAG answers flagged for human review)
 *  - Jaeger deep-link        (full distributed-trace tree)
 *
 * Why this completes the loop: the propagator + middleware (commits
 * f8f0ba5 + f3106d1) carry baggage.request_id across services; the
 * log formatter (4876fa1) gets it into every log line; the endpoint
 * (9012c7a) joins all 3 governance tables. This page is the human
 * surface for that pipeline.
 *
 * Stays 200 even with zero matches: an unknown (correlation_id,
 * tenant_id) is a normal "I'm investigating, nothing happened
 * yet" state. We surface empty + db_reachable=true clearly.
 */

import Link from 'next/link';
import { useCallback, useRef, useState } from 'react';

import DeepDiveCrossRefs from '../../../components/DeepDiveCrossRefs';
import {
  api,
  ApiError,
  type TraceLinkResponse,
} from '../../../lib/api';

function statusBadgeClass(status: string): string {
  if (status === 'pending') return 'badge badge-parsing';
  if (status === 'replayed' || status === 'approved') return 'badge badge-active';
  if (status === 'rejected') return 'badge badge-failed';
  if (status === 'edited') return 'badge badge-active';
  return 'badge';
}

function reviewBadgeClass(status: string): string {
  if (status === 'pending') return 'badge badge-parsing';
  if (status === 'approved') return 'badge badge-active';
  if (status === 'rejected') return 'badge badge-failed';
  if (status === 'edited') return 'badge badge-active';
  return 'badge';
}

const UUID_RX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function ForensicsPage() {
  const [correlationId, setCorrelationId] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [data, setData] = useState<TraceLinkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const lookup = useCallback(async () => {
    const cid = correlationId.trim();
    const tid = tenantId.trim();
    if (!cid || !tid) {
      setError('Both correlation_id and tenant_id are required.');
      return;
    }
    if (!UUID_RX.test(cid)) {
      setError('correlation_id must be a UUID.');
      return;
    }
    if (!UUID_RX.test(tid)) {
      setError('tenant_id must be a UUID.');
      return;
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setError(null);
    try {
      const resp = await api.traceLink(cid, tid, ac.signal);
      setData(resp);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg =
        err instanceof ApiError
          ? `${err.status}: ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      setError(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [correlationId, tenantId]);

  const isEmpty =
    data
    && data.audit_rows.length === 0
    && data.draft_rows.length === 0
    && data.hitl_rows.length === 0;

  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Forensics — trace → draft → audit → HITL</h1>
        <p className="design-areas-sub">
          Paste a correlation_id and the tenant it belongs to. We join{' '}
          <code>governance.audit_log</code>, <code>governance.action_drafts</code>,
          and <code>governance.hitl_queue</code> by{' '}
          <code>correlation_id</code>, plus link out to Jaeger for the full
          distributed-trace tree. Operators land here from a user complaint,
          an alert, or a draft / HITL ticket.
        </p>
      </header>

      <section className="card" style={{ marginTop: 16 }}>
        <strong>Lookup</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr auto',
            gap: 12,
            marginTop: 12,
            alignItems: 'end',
          }}
        >
          <label style={{ display: 'flex', flexDirection: 'column', fontSize: 13 }}>
            <span style={{ color: '#475569', marginBottom: 4 }}>
              correlation_id (UUID)
            </span>
            <input
              type="text"
              value={correlationId}
              onChange={(e) => setCorrelationId(e.target.value)}
              placeholder="e.g. 0123abcd-... (from X-Correlation-ID header)"
              style={{
                padding: '8px 10px',
                border: '1px solid #cbd5e1',
                borderRadius: 4,
                fontFamily: 'ui-monospace, monospace',
                fontSize: 13,
              }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', fontSize: 13 }}>
            <span style={{ color: '#475569', marginBottom: 4 }}>
              tenant_id (UUID — required, RLS-scoped)
            </span>
            <input
              type="text"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="tenant UUID from auth context"
              style={{
                padding: '8px 10px',
                border: '1px solid #cbd5e1',
                borderRadius: 4,
                fontFamily: 'ui-monospace, monospace',
                fontSize: 13,
              }}
            />
          </label>
          <button
            type="button"
            onClick={lookup}
            disabled={loading}
            style={{
              padding: '8px 16px',
              background: loading ? '#94a3b8' : '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              fontSize: 14,
              fontWeight: 500,
              cursor: loading ? 'wait' : 'pointer',
            }}
          >
            {loading ? 'Looking up…' : 'Look up'}
          </button>
        </div>
        <p style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
          Tenant is required because <code>audit_log</code> RLS is
          FORCE-enabled and the documind_app role is non-BYPASSRLS — the
          backend honestly scopes lookups per-tenant rather than pretending
          cross-tenant access works.
        </p>
      </section>

      {error && (
        <div
          className="card"
          role="alert"
          style={{
            marginTop: 16,
            background: '#fef2f2',
            borderLeft: '4px solid #dc2626',
          }}
        >
          <strong style={{ color: '#991b1b' }}>Error:</strong>{' '}
          <span style={{ color: '#7f1d1d' }}>{error}</span>
        </div>
      )}

      {data && (
        <>
          <section
            className="card"
            style={{
              marginTop: 16,
              background: data.db_reachable ? '#f0fdf4' : '#fffbeb',
              borderLeft: `4px solid ${data.db_reachable ? '#16a34a' : '#d97706'}`,
            }}
          >
            <strong>
              correlation_id:{' '}
              <code style={{ fontFamily: 'ui-monospace, monospace' }}>
                {data.correlation_id}
              </code>
            </strong>
            <div style={{ marginTop: 8, fontSize: 13, color: '#475569' }}>
              <span>observed at {data.observed_at}</span>
              {' · '}
              <span>
                governance DB:{' '}
                <strong style={{ color: data.db_reachable ? '#15803d' : '#b45309' }}>
                  {data.db_reachable ? 'reachable' : 'unreachable'}
                </strong>
              </span>
              {' · '}
              <span>{data.audit_rows.length} audit</span>
              {' · '}
              <span>{data.draft_rows.length} drafts</span>
              {' · '}
              <span>{data.hitl_rows.length} HITL</span>
            </div>
            {data.jaeger_url && (
              <div style={{ marginTop: 12 }}>
                <a
                  href={data.jaeger_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-block',
                    padding: '6px 12px',
                    background: '#1e3a8a',
                    color: 'white',
                    textDecoration: 'none',
                    borderRadius: 4,
                    fontSize: 13,
                    fontWeight: 500,
                  }}
                >
                  Open in Jaeger →
                </a>
              </div>
            )}
            {!data.db_reachable && (
              <p
                style={{
                  marginTop: 8,
                  fontSize: 13,
                  color: '#92400e',
                  background: '#fef3c7',
                  padding: 8,
                  borderRadius: 4,
                }}
              >
                Governance database wasn&apos;t reachable when this lookup ran.
                Audit + draft + HITL arrays may be incomplete. Retry once
                the DB is back.
              </p>
            )}
            {isEmpty && data.db_reachable && (
              <p
                style={{
                  marginTop: 8,
                  fontSize: 13,
                  color: '#475569',
                  fontStyle: 'italic',
                }}
              >
                No rows match this (correlation_id, tenant_id) pair. Either
                the request hasn&apos;t reached governance yet, the tenant is
                wrong, or the correlation_id is from a different tenant&apos;s
                trace.
              </p>
            )}
          </section>

          {data.audit_rows.length > 0 && (
            <section className="card" style={{ marginTop: 16 }}>
              <strong>Audit log ({data.audit_rows.length})</strong>
              <div style={{ overflowX: 'auto', marginTop: 12 }}>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #cbd5e1', textAlign: 'left' }}>
                      <th style={{ padding: '6px 8px' }}>timestamp</th>
                      <th style={{ padding: '6px 8px' }}>action</th>
                      <th style={{ padding: '6px 8px' }}>actor</th>
                      <th style={{ padding: '6px 8px' }}>resource</th>
                      <th style={{ padding: '6px 8px' }}>fail-closed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.audit_rows.map((row) => (
                      <tr
                        key={row.id}
                        style={{ borderBottom: '1px solid #e2e8f0' }}
                      >
                        <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                          {row.timestamp}
                        </td>
                        <td style={{ padding: '6px 8px' }}>{row.action}</td>
                        <td style={{ padding: '6px 8px', fontSize: 12 }}>
                          {row.actor_type}
                          {row.actor_id ? ` · ${row.actor_id.slice(0, 8)}…` : ''}
                        </td>
                        <td style={{ padding: '6px 8px', fontSize: 12 }}>
                          {row.resource_type ?? '—'}
                          {row.resource_id ? ` · ${row.resource_id.slice(0, 8)}…` : ''}
                        </td>
                        <td style={{ padding: '6px 8px' }}>
                          {row.fail_closed_failed ? (
                            <span className="badge badge-failed">FAILED</span>
                          ) : (
                            <span style={{ color: '#94a3b8' }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {data.draft_rows.length > 0 && (
            <section className="card" style={{ marginTop: 16 }}>
              <strong>Action drafts ({data.draft_rows.length})</strong>
              <div style={{ overflowX: 'auto', marginTop: 12 }}>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #cbd5e1', textAlign: 'left' }}>
                      <th style={{ padding: '6px 8px' }}>draft_id</th>
                      <th style={{ padding: '6px 8px' }}>tool</th>
                      <th style={{ padding: '6px 8px' }}>status</th>
                      <th style={{ padding: '6px 8px' }}>reason</th>
                      <th style={{ padding: '6px 8px' }}>created</th>
                      <th style={{ padding: '6px 8px' }}>replayed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.draft_rows.map((row) => (
                      <tr
                        key={row.draft_id}
                        style={{ borderBottom: '1px solid #e2e8f0' }}
                      >
                        <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                          {row.draft_id}
                        </td>
                        <td style={{ padding: '6px 8px' }}>{row.tool}</td>
                        <td style={{ padding: '6px 8px' }}>
                          <span className={statusBadgeClass(row.status)}>{row.status}</span>
                        </td>
                        <td style={{ padding: '6px 8px', fontSize: 12 }}>{row.reason}</td>
                        <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                          {row.created_at}
                        </td>
                        <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                          {row.replayed_at ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {data.hitl_rows.length > 0 && (
            <section className="card" style={{ marginTop: 16 }}>
              <strong>
                HITL queue ({data.hitl_rows.length}) — human-review evidence
              </strong>
              <p style={{ marginTop: 4, marginBottom: 12, fontSize: 12, color: '#64748b' }}>
                Non-empty means human-in-the-loop intervened — the EU AI Act
                Art. 14 (human oversight) audit trail.
              </p>
              <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #cbd5e1', textAlign: 'left' }}>
                    <th style={{ padding: '6px 8px' }}>id</th>
                    <th style={{ padding: '6px 8px' }}>question</th>
                    <th style={{ padding: '6px 8px' }}>conf</th>
                    <th style={{ padding: '6px 8px' }}>flag reason</th>
                    <th style={{ padding: '6px 8px' }}>review</th>
                    <th style={{ padding: '6px 8px' }}>reviewer</th>
                  </tr>
                </thead>
                <tbody>
                  {data.hitl_rows.map((row) => (
                    <tr
                      key={row.id}
                      style={{ borderBottom: '1px solid #e2e8f0' }}
                    >
                      <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                        {row.id.slice(0, 8)}…
                      </td>
                      <td style={{ padding: '6px 8px', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={row.question}>
                        {row.question}
                      </td>
                      <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                        {row.confidence !== null && row.confidence !== undefined
                          ? row.confidence.toFixed(3)
                          : '—'}
                      </td>
                      <td style={{ padding: '6px 8px', fontSize: 12 }}>
                        {row.flag_reason ?? '—'}
                      </td>
                      <td style={{ padding: '6px 8px' }}>
                        <span className={reviewBadgeClass(row.review_status)}>
                          {row.review_status}
                        </span>
                      </td>
                      <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                        {row.reviewer_id ? `${row.reviewer_id.slice(0, 8)}…` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      <DeepDiveCrossRefs
        refs={[
          {
            href: '/admin/tracing/deep#trace-draft-audit-linkage',
            label: 'Tracing — trace → draft → audit by request_id',
            why: 'this page is the operator UI for the documented forensics pattern; baggage.request_id from upstream services flows here as the lookup key',
          },
          {
            href: '/admin/explainability/deep#audit-rag-contract-regulation',
            label: 'Explainability — RAG four-part + audit row schema',
            why: 'audit_log + drafts + HITL + Jaeger together satisfy EU AI Act Art. 14 (human oversight) + Art. 86 (right to explanation)',
          },
          {
            href: '/admin/checklist/deep#governance-ops-checklist',
            label: 'Checklist — hard-stop #5 (no tracing)',
            why: 'this page exists to prove the no-tracing hard-stop is satisfied: paste a request_id, see the chain end-to-end',
          },
          {
            href: '/admin/llmops/deep',
            label: 'LLMOps — model + prompt registry',
            why: 'audit row carries model_version + prompt_version; click-through to registry from a forensics finding closes the explainability loop',
          },
          {
            href: '/admin/security/deep#cloud-soc2-iam',
            label: 'Security — SOC2 CC6.1 + RLS',
            why: 'tenant_id is required because audit_log RLS is FORCE-enabled — this page is the honest, per-tenant lookup surface',
          },
        ]}
      />

      <p style={{ marginTop: 16, fontSize: 12, color: '#64748b' }}>
        Tip: copy the correlation_id from the <code>X-Correlation-ID</code> response
        header that every API call echoes (set by{' '}
        <Link href="/admin/tracing/deep#baggage-propagation" style={{ color: '#2563eb' }}>
          BaggageContextMiddleware
        </Link>
        ).
      </p>
    </div>
  );
}
