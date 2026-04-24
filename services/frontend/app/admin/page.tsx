export default function AdminPage() {
  return (
    <>
      <h1 className="section-title">Admin</h1>
      <div className="card">
        <p>
          Admin panels map to the governance + observability + finops services.
          This page is a placeholder for the demo - the real implementation
          lives under <code>services/governance-svc</code> and friends.
        </p>
        <ul
          style={{
            marginTop: 12,
            paddingLeft: 20,
            color: 'var(--text-secondary)',
          }}
        >
          <li>Model Control Portal (MCP): <code>GET /api/v1/admin/models</code></li>
          <li>HITL queue: <code>GET /api/v1/admin/hitl/queue</code></li>
          <li>Policies: <code>GET /api/v1/admin/policies</code></li>
          <li>FinOps usage: <code>GET /api/v1/admin/finops/usage</code></li>
          <li>SLO dashboard: <code>GET /api/v1/admin/slo</code></li>
        </ul>
      </div>
    </>
  );
}
