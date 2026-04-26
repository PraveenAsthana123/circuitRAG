'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'rbac-abac',
    title: '1. RBAC + ABAC — role + attribute-based access control',
    status: 'shipped',
    coreConcept: 'RBAC binds permissions to roles; users inherit via group membership. ABAC adds runtime attributes (tenant_id, resource_owner, time-of-day) to the policy. The platform enforces both at three layers: gateway (coarse), service (mid), database (fine via RLS).',
    oneLiner: 'RBAC = role → permissions; ABAC = attributes refine; defense in depth at gateway + service + DB.',
    businessContext: 'Multi-tenant SaaS with regulated customers needs auditable access control that survives one missed app-layer check. Without layered enforcement, a single bug = compliance breach.',
    fiveW: {
      what: 'A 3-layer enforcement: gateway scopes JWT claims, service routes apply RBAC role check, database enforces RLS using tenant_id + actor.',
      why: 'Single-layer access control has one point of failure. Three layers means a bug in one is caught by the next.',
      where: 'Gateway: scopes claim from JWT. Service: @requires_role decorator on routes. DB: RLS policies + role separation (NOBYPASSRLS app role).',
      when: 'Always for multi-tenant SaaS; mandatory for regulated tiers.',
      who: 'Identity team owns role catalog. Each service team enforces. Security audits + drills.',
    },
    interview30s: 'Access control is layered. Gateway extracts scopes from the JWT. Service routes use @requires_role decorators with RBAC role check. Database enforces RLS using current_setting(\'app.current_tenant\') in policies. ABAC adds attributes — resource ownership, time, IP — at the service layer. The non-negotiable test is a drill that hits a protected endpoint with an undersized role and asserts 403, then with a missing tenant_id and asserts empty result from DB.',
    coreBuildingBlocks: [
      'JWT scopes claim — coarse gate at gateway',
      'Role catalog — per-tenant, mapped from IdP groups',
      '@requires_role decorator — service-layer check',
      'ABAC attribute resolver — request → tenant_id, actor, resource_owner',
      'RLS policies — DB-layer enforcement',
      'Audit chain — every denied + allowed access logged',
    ],
    flowchart: `flowchart LR
  REQ[Request + JWT] --> GW[api-gateway]
  GW -->|verify scopes claim| SCP{scope ok?}
  SCP -->|no| D1[403 deny]
  SCP -->|yes| SVC[Service]
  SVC -->|requires_role| RBAC{role ok?}
  RBAC -->|no| D2[403 deny + audit]
  RBAC -->|yes| ABAC{ABAC attributes match?}
  ABAC -->|no| D3[403 deny + audit]
  ABAC -->|yes| DB["DB query with SET LOCAL app.current_tenant"]
  DB -->|RLS filter| OUT[Authorized result]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant GW as Gateway
  participant Svc as Service
  participant Aud as Audit
  participant DB as DB with RLS
  U->>GW: request + JWT
  GW->>GW: verify signature + scopes claim
  alt scope insufficient
    GW-->>U: 403
    GW->>Aud: log scope deny
  else ok
    GW->>Svc: forward + tenant + scopes
    Svc->>Svc: requires_role check
    Svc->>Svc: ABAC attribute check
    alt RBAC ok and ABAC ok
      Svc->>DB: BEGIN + SET LOCAL app.current_tenant
      DB->>DB: apply RLS policies
      DB-->>Svc: rows or empty
      Svc-->>U: response
      Svc->>Aud: log allowed access
    else deny
      Svc-->>U: 403
      Svc->>Aud: log deny with reason
    end
  end`,
    coreLayers: [
      { layer: 'Gateway scope', responsibility: 'Coarse-gate by JWT scopes claim. Reject early on insufficient scope. Cheap; runs first.' },
      { layer: 'Service RBAC', responsibility: '@requires_role(role) decorator on routes. Role catalog per-tenant. Maps from IdP groups via SSO + LDAP.' },
      { layer: 'Service ABAC', responsibility: 'Runtime attributes — tenant_id, resource_owner, IP, time. Policy expressions evaluated per request.' },
      { layer: 'DB RLS', responsibility: 'app role NOBYPASSRLS; ops role BYPASSRLS audited. Policies use current_setting(app.current_tenant).' },
      { layer: 'Audit', responsibility: 'Every deny + allow with reason + actor + correlation_id. Hash-chained per tenant.' },
    ],
    problem: 'Single-layer auth has one point of failure. App-only checks miss DB-layer queries; DB-only misses business rules; gateway-only is too coarse. Three-layer defense is the structural answer.',
    whyThisApproach: 'Defense in depth — a bug in any one layer is caught by the next. Audit chain proves compliance to auditors. Layered enforcement matches every regulator\'s expectation.',
    whenToUse: ['Multi-tenant SaaS', 'Regulated industries (HIPAA, SOC2, GDPR)', 'Customers with BYOD admin access', 'Any system where a leak = contract loss'],
    whenNotToUse: ['Single-tenant internal tooling', 'Read-only public APIs', 'Trust-implicit prototypes'],
    input: 'JWT (scopes, sub, tenant_id) + request resource path + body',
    process: [
      'Gateway: extract scopes from JWT; reject 403 if insufficient',
      'Service: @requires_role checks the JWT role claim against catalog',
      'Service: ABAC resolver evaluates per-request attributes',
      'Service: open DB connection with SET LOCAL app.current_tenant',
      'DB: RLS policy filters rows by tenant_id (or rejects insert)',
      'Audit: log decision (allow / deny + reason + correlation_id)',
    ],
    output: 'Authorized response OR 403 with reason. Audit row written either way.',
    alternatives: [
      { name: 'Pure RBAC (no ABAC)', tradeoff: 'Simple; can\'t express resource-ownership rules; static-role explosion at scale' },
      { name: 'Pure ABAC (no RBAC)', tradeoff: 'Flexible; harder to audit; performance concern on attribute resolution' },
      { name: 'OPA / Cedar (policy engine)', tradeoff: 'Express policies in DSL; ops overhead; cross-cutting visibility' },
      { name: 'AWS IAM-only', tradeoff: 'Vendor-tied; not portable; doesn\'t cover app-layer business rules' },
    ],
    challenges: [
      'Role catalog explosion at high tenant count',
      'ABAC attribute resolution latency',
      'IdP group mapping drift',
      'BYPASSRLS misuse in admin paths',
      'Audit chain integrity at scale',
    ],
    edgeCases: [
      { case: 'User in multiple tenants', solution: 'Per-tenant scoped JWT; switch tenant = new login OR explicit scope claim' },
      { case: 'Resource owner != tenant owner', solution: 'ABAC checks resource_owner attribute; document ownership model' },
      { case: 'Admin needs cross-tenant query', solution: 'documind_ops role with audit row + reason field' },
      { case: 'RBAC role removed mid-session', solution: 'Token introspection or short-lived JWT (1h) + refresh check' },
    ],
    failureModes: [
      { mode: 'Cross-tenant leak via missing app.current_tenant', detect: 'drill_retrieval_tenant_isolation red', recover: 'Quarantine endpoint; restore middleware; ship drill to CI' },
      { mode: 'BYPASSRLS in app role', detect: 'Audit shows app role with BYPASSRLS', recover: 'Revoke; re-grant NOBYPASSRLS only' },
      { mode: 'Role catalog drift vs IdP', detect: 'Periodic compare; alert on mismatch', recover: 'Reconcile; document in ADR' },
    ],
    monitoring: [
      'RBAC deny rate per route',
      'ABAC attribute resolver latency',
      'Audit chain integrity drill',
      'BYPASSRLS query count per tenant per day',
      'IdP role-mapping drift events',
    ],
    testing: [
      'Drill: undersized role hits protected endpoint → 403',
      'Drill: missing tenant_id → empty DB result',
      'Drill: BYPASSRLS query without audit row → drill red',
      'Drill: role removed mid-session → next request 403',
    ],
    security: [
      'NOBYPASSRLS app role; BYPASSRLS ops role audited',
      'JWT signed; short-lived (1h); refresh tokens',
      'Audit chain hash-chained per tenant',
      'Role grants reviewed quarterly',
    ],
    scaling: [
      'Role lookup: cached in Redis with TTL',
      'ABAC resolver: per-request evaluation, ~5ms',
      'RLS overhead: < 1ms per query with proper indexes',
    ],
    maturity: {
      mvp: 'Single role per user; manual policy',
      production: '3-layer enforcement + RLS + audit chain + drills',
      enterprise: 'OPA / Cedar policy engine + per-tenant role catalog + automated compliance evidence',
    },
    limitations: [
      'Role catalog explosion at very high tenant count',
      'ABAC resolution adds per-request latency',
      'Audit chain storage grows linearly',
    ],
    projectFit: [
      'libs/py/documind_core/auth.py — JWT verify + scopes',
      'libs/py/documind_core/rbac.py — @requires_role decorator',
      'governance.audit_log — decision audit',
      'mcp/tests/drill_rbac_*.py — per-layer drills',
    ],
    interviewLine: 'Access control is three layers — gateway scopes, service RBAC + ABAC, database RLS — with an audit chain across all three. A bug in one layer is caught by the next. The drill is non-negotiable: undersized role → 403, missing tenant_id → empty result.',
    finalScript: 'Access control is defense in depth across three layers. Gateway extracts JWT scopes for coarse-grained gating — reject early on insufficient scope. Service applies @requires_role decorators backed by per-tenant role catalogs mapped from IdP groups via SSO + LDAP. Service ABAC resolves runtime attributes — tenant_id, resource_owner, IP, time-of-day — and evaluates per-request policies. Database enforces row-level security: app role is NOBYPASSRLS, ops role is BYPASSRLS but every operation writes an audit row with the actor and reason. Audit chain is hash-chained per tenant. The drill is non-negotiable: undersized role hitting a protected endpoint must return 403; missing tenant_id at the DB must return empty rows. Mocks lie about RLS; only the live cluster catches the leak.',
  },
];

export default function RbacDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">RBAC + ABAC — Deep Dive</h1>
        <p className="design-areas-sub">
          Three-layer access control: gateway scopes + service RBAC/ABAC + database RLS.
          Audit chain across all three. Drill-locked.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
