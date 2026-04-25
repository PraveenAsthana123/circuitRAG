export default function AdminPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Admin</h1>
          <p className="page-subtitle">
            Operator entry point for governance, observability, human review, and cost controls.
            This is still a thin surface, but it should behave like a real landing page instead of a dead placeholder.
          </p>
        </div>
      </div>

      <div className="metrics-strip">
        <div className="metric-card">
          <div className="metric-label">MCP control</div>
          <div className="metric-value">Ready</div>
          <div className="field-help">Model and tool inventory APIs are intended to surface here.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">HITL queue</div>
          <div className="metric-value">Planned</div>
          <div className="field-help">Queue triage UI is not implemented in this frontend yet.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Policy ops</div>
          <div className="metric-value">Planned</div>
          <div className="field-help">Policy review, denial analysis, and rollout controls belong here.</div>
        </div>
      </div>

      <div className="card stack">
        <div>
          <strong>Available admin API surfaces</strong>
          <div className="field-help" style={{ marginTop: 8 }}>
            The backend contracts exist conceptually; this page is where the live UI should be attached.
          </div>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Area</th>
                <th>Endpoint</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>MCP</td>
                <td><code>GET /api/v1/admin/models</code></td>
                <td>Model Control Portal inventory and provider status.</td>
              </tr>
              <tr>
                <td>HITL</td>
                <td><code>GET /api/v1/admin/hitl/queue</code></td>
                <td>Human review queue for escalated or blocked actions.</td>
              </tr>
              <tr>
                <td>Policies</td>
                <td><code>GET /api/v1/admin/policies</code></td>
                <td>Governance rules, versions, and rollout state.</td>
              </tr>
              <tr>
                <td>FinOps</td>
                <td><code>GET /api/v1/admin/finops/usage</code></td>
                <td>Token, request, and tenant-spend visibility.</td>
              </tr>
              <tr>
                <td>SLOs</td>
                <td><code>GET /api/v1/admin/slo</code></td>
                <td>Reliability, latency, and degradation tracking.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card stack" style={{ marginTop: 24 }}>
        <strong>UI Gaps Still Open</strong>
        <ul style={{ paddingLeft: 20, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <li>Live cards for breaker state, pending drafts, and queue age</li>
          <li>Policy editing and rollout controls</li>
          <li>HITL item review and resolution workflow</li>
          <li>Operational drill and incident evidence views</li>
        </ul>
      </div>
    </>
  );
}
