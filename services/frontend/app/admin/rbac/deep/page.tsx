'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
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
    implementationSteps: [
      { step: 'Gateway: JWT scope check', logic: 'Coarse-grained; reject early on insufficient scope before service hop.' },
      { step: 'Service RBAC: @requires_role', logic: 'Per-tenant role catalog mapped from IdP groups; decorator at every protected route.' },
      { step: 'Service ABAC: attribute eval', logic: 'tenant_id + resource_owner + IP + time-of-day evaluated per request.' },
      { step: 'DB RLS: NOBYPASSRLS app role', logic: 'tenant_connection() sets app.current_tenant_id; policy applied to every query.' },
      { step: 'Ops role: BYPASSRLS + audit', logic: 'Every BYPASSRLS op writes a hash-chained audit row with actor + reason.' },
      { step: 'Per-layer drill', logic: 'Undersized role → 403; missing tenant_id → empty rows; ops without audit → 503.' },
      { step: 'Audit chain seal', logic: 'HMAC chain per tenant; periodic verification gate.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/auth.py — three-layer access control
from functools import wraps
from fastapi import Depends, HTTPException, Request
from libs.py.documind_core.exceptions import ForbiddenError

# LAYER 1: Gateway scope check (api-gateway/main.go in real; shown in py)
def require_scope(scope: str):
    """Coarse-grained: reject early on insufficient scope."""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: Request, *args, **kwargs):
            jwt_scopes: set[str] = request.state.jwt.get("scopes", set())
            if scope not in jwt_scopes:
                raise ForbiddenError(f"missing scope: {scope}")
            return await handler(request, *args, **kwargs)
        return wrapper
    return decorator

# LAYER 2: Service RBAC + ABAC
def requires_role(*allowed_roles: str):
    """Fine-grained: role check + ABAC attributes."""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: Request, *args, **kwargs):
            user = request.state.user
            if not set(user.roles) & set(allowed_roles):
                raise ForbiddenError(f"role required: {allowed_roles}")
            # ABAC: enforce same-tenant + business hours for "purge"
            if "ops_purge" in allowed_roles:
                if user.tenant_id != kwargs.get("target_tenant_id"):
                    raise ForbiddenError("cross-tenant op not permitted")
            return await handler(request, *args, **kwargs)
        return wrapper
    return decorator

# LAYER 3: Database RLS — set in tenant_connection()
@router.delete("/api/v1/admin/tenants/{target_tenant_id}/purge")
@require_scope("admin:write")           # gateway-equivalent
@requires_role("ops_purge")              # service RBAC + ABAC
async def admin_purge(
    target_tenant_id: str,
    pool = Depends(get_pool),
    user: User = Depends(get_user),
):
    # DB RLS: ops role + audit on every BYPASSRLS op
    async with tenant_connection(pool, target_tenant_id, role="documind_ops") as conn:
        deleted = await conn.fetchval(
            "DELETE FROM chunks WHERE tenant_id = $1 RETURNING count(*)",
            target_tenant_id,
        )
        await audit_chain_write(
            conn, tenant_id=target_tenant_id, actor_id=user.id,
            action="admin_purge", payload={"deleted": deleted},
        )
        return {"deleted": deleted}`,
    },
    realUseCase: 'A new admin endpoint shipped without the @requires_role decorator. drill_rbac_three_layers caught it: gateway accepted (admin scope present), service did NOT 403, but DB RLS returned empty rows because the role was app (NOBYPASSRLS). Defense in depth saved the day. Drill flagged the missing service-layer check; PR added @requires_role; layered tests now pass.',
    prosCons: {
      pros: [
        'Three layers = defense in depth (one bug doesn\'t leak)',
        'DB RLS is a database invariant, not app discipline',
        'Per-tenant role catalogs support customer-specific RBAC',
        'ABAC handles runtime attributes (time, location, owner)',
        'Hash-chained audit makes admin ops reconstructible',
      ],
      cons: [
        'Overhead: ~3-5ms per request across all 3 layers',
        'Per-tenant role catalog grows ops surface',
        'BYPASSRLS+audit is heavier than simple BYPASSRLS — but safer',
        'ABAC complexity grows with policy variety',
      ],
    },
    comparison: {
      left: 'App-layer WHERE clause only',
      right: 'Three-layer + DB RLS (this)',
      rows: [
        { aspect: 'Cross-tenant leak risk', left: 'High — one missed JOIN', right: 'Low — DB invariant' },
        { aspect: 'Layer-skip bypass', left: 'No defense', right: 'Caught by next layer' },
        { aspect: 'Admin op auditability', left: 'Optional', right: 'Required, hash-chained' },
        { aspect: 'Per-tenant customization', left: 'Hardcoded roles', right: 'Per-tenant catalog from IdP' },
        { aspect: 'ABAC support', left: 'Ad-hoc per endpoint', right: 'Centralized policy eval' },
      ],
    },
    solutions: [
      { problem: 'Missed @requires_role on new endpoint', solution: 'Drill catches it via DB RLS empty-rows result' },
      { problem: 'Cross-tenant admin op leak', solution: 'BYPASSRLS only via documind_ops role + mandatory audit' },
      { problem: 'Stale RBAC after offboarding', solution: 'LDAP tombstone + Redis pub/sub invalidates JWT-cache' },
      { problem: 'Time-of-day attack', solution: 'ABAC time check; production purge ops gated to business hours' },
      { problem: 'Compromised JWT', solution: 'Short TTL + audience binding to tenant_id' },
    ],
    bestPractices: {
      do: [
        'Three layers: gateway scope + service RBAC/ABAC + DB RLS',
        'NOBYPASSRLS on app role; BYPASSRLS on documind_ops only',
        'Audit every BYPASSRLS op with actor + reason',
        'Per-tenant role catalog mapped from IdP groups',
        'Drill catches single-layer regressions',
      ],
      avoid: [
        'BYPASSRLS in user-facing service role',
        'App-layer WHERE as the only tenant filter',
        'Single role catalog across tenants',
        'Logging admin ops without hash-chain',
        'Skipping the layer-skip drill — claim defense in depth, prove it',
      ],
      optimize: [
        'Cache role resolution per JWT (TTL = JWT TTL)',
        'Pre-evaluate ABAC policies at JWT mint where possible',
        'Read replicas for ABAC attribute lookup (time, location)',
        'Async audit batch flush (≤ 200ms behind transaction commit)',
      ],
    },
    antiPatterns: [
      'BYPASSRLS in user-facing service role',
      'Single-layer access control (one bug = leak)',
      'Hardcoded global role catalog',
      'Admin ops without audit',
      'JWT TTL > 24 hours with no refresh',
      'Skipping ABAC — coarse RBAC is not enough for time/location/owner checks',
    ],
    testTypes: [
      'Drill: insufficient scope at gateway → 401/403',
      'Drill: undersized role at service → 403',
      'Drill: missing tenant_id at DB → empty rows',
      'Drill: BYPASSRLS without audit → 503',
      'Drill: cross-tenant attempt via leaked JWT → audit + 403',
      'Drill: audit chain seal verification across all layers',
    ],
    testScenarios: [
      { scenario: 'User without admin:write scope hits admin endpoint', expected: '403 at gateway; audit row noting denial' },
      { scenario: 'Wrong tenant_id forwarded by service', expected: 'DB RLS returns empty rows; service 200 with empty list' },
      { scenario: 'Admin runs purge during off-hours', expected: 'ABAC time check 403; audit row' },
      { scenario: 'BYPASSRLS op skipped audit write', expected: 'Service returns 503; transaction rolled back' },
      { scenario: 'Audit chain HMAC fails verification', expected: 'drill_audit_seal red; investigation triggered' },
    ],
    testData: [
      { type: 'Multi-tenant fixture', example: '4 tenants × users with various roles; cross-tenant attempts seeded' },
      { type: 'Admin role catalog fixture', example: 'Per-tenant catalog: ops_read / ops_write / ops_purge with ABAC bounds' },
      { type: 'Audit chain seed', example: 'Pre-sealed window per tenant with HMAC; verifier must accept' },
    ],
    debuggingChecklist: [
      'Cross-tenant rows? Check tenant_connection() usage; check role NOBYPASSRLS',
      'Stuck 403? Compare JWT scopes vs route requirements',
      'Audit row missing? BYPASSRLS without audit_chain_write → service should 503',
      'Slow auth? Cache JWT role resolution; check pool wait time',
      'JWT replay? Check TTL + refresh-token rotation',
    ],
    productionIssues: [
      { issue: 'New endpoint shipped without @requires_role decorator', rootCause: 'Code review missed; drill caught at PR via empty-rows test. PR fixed.' },
      { issue: 'BYPASSRLS used in runtime path; cross-tenant leak', rootCause: 'Engineer hot-fixed an issue with documind_ops role; never reverted. Audit row showed leak. Reverted + added drill_no_runtime_bypass.' },
      { issue: '24h JWT replay after offboarding', rootCause: 'JWT TTL 24h; offboarding tombstone happened but old JWT kept working. Reduced TTL to 1h; added pub/sub invalidation.' },
    ],
    performance: [
      'Gateway scope check: ~0.5ms (JWT pre-decoded)',
      'Service RBAC + ABAC: ~2-3ms (catalog lookup + policy eval)',
      'DB RLS overhead: ~2-4% query time (policy eval)',
      'Audit write: async ~10ms p95; doesn\'t block response',
    ],
    costConsiderations: [
      'Compute: ~3-5ms per request × N requests = small',
      'Audit storage: ~500 bytes per BYPASSRLS row × retention',
      'Per-tenant catalog: small JSON in PG; no separate store needed',
    ],
    observability: [
      'Trace: per-request with all 3 layers + decisions',
      'Metrics: rbac_denial_total{layer,reason}, audit_write_failures_total',
      'Logs: structured with correlation_id + tenant_id + actor_id',
      'Audit: hash-chained per tenant; verified by drill_audit_seal',
    ],
    metrics: [
      { name: 'documind_rbac_denial_total{layer,reason}', example: 'Counter; spike on layer=db may indicate missing decorator regression' },
      { name: 'documind_bypassrls_op_total{actor,table}', example: 'Counter; review weekly for unexpected actors' },
      { name: 'documind_audit_chain_verifications{tenant,outcome}', example: 'Counter; alert if outcome=fail at any value > 0' },
      { name: 'documind_jwt_replay_attempts_total', example: 'Counter; high count = active attack or stolen tokens' },
    ],
    tradeoffs: [
      { decision: 'NOBYPASSRLS app role', tradeoff: 'Stricter isolation; admin ops require role switch + audit' },
      { decision: 'JWT TTL', tradeoff: 'Short = more refresh load; long = larger blast radius' },
      { decision: 'ABAC complexity', tradeoff: 'Rich policies = better; harder to monitor + tune' },
      { decision: 'Audit hash-chain vs append-only', tradeoff: 'Tamper-evident; ~1.3x write amplification' },
    ],
    decisionMatrix: [
      { option: 'Three-layer + DB RLS (this)', whenToUse: 'Multi-tenant SaaS, audit-grade, regulatory' },
      { option: 'Two-layer (gateway + service)', whenToUse: 'Single-tenant, no DB-level isolation' },
      { option: 'Vendor IAM (e.g., Cerbos, OPA)', whenToUse: 'Heavy policy-as-code; willing to operate sidecar' },
    ],
    starStory: {
      situation: 'Compliance customer flagged that admin "purge-tenant" endpoint could read another tenant\'s data via implicit BYPASSRLS — even though it never had in production.',
      task: 'Eliminate implicit BYPASSRLS path while keeping admin operability.',
      action: 'Split DB role into app (NOBYPASSRLS) and documind_ops (BYPASSRLS, audited). Wrapped admin paths in tenant_connection(role="documind_ops"). Audit row before every BYPASSRLS query. drill_admin_audit asserts: (1) admin op without audit fails 503, (2) chain HMAC verifies post-op.',
      result: 'Compliance customer accepted architecture. drill_admin_audit added to CI; gates main. Zero compliance findings in subsequent quarterly review. ADR-007 documented; pattern adopted by 3 other internal services.',
    },
    interviewTraps: [
      'Saying "we use RLS" without specifying FORCE',
      'Single-layer access control with no drill',
      'BYPASSRLS in user-facing service role',
      'Admin ops without hash-chained audit',
      'JWT replay risk via long TTL + no refresh',
    ],
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
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/sso/deep', label: 'SSO (SAML / OIDC)', why: 'group claims from IdP map to RBAC roles via JIT provisioning; RBAC is the layer that consumes SSO claims' },
          { href: '/admin/ldap/deep', label: 'LDAP (enterprise sync)', why: 'enterprise group memberships sync via LDAP → RBAC role assignments; ldap-svc is the source of truth' },
          { href: '/admin/security/deep#cloud-soc2-iam', label: 'SOC2 CC6.1 access control', why: 'RBAC + role review + audit log = SOC2 access-control evidence trail; CC6.1 maps directly' },
          { href: '/admin/tracing/deep#trace-draft-audit-linkage', label: 'Audit by request_id', why: 'every authz decision logged with actor + scope + decision; forensics filterable by tenant + actor' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Hard-stop #1 (security issue)', why: 'broken access control is OWASP A01 + the #1 hard stop; release blocked until RBAC tests green' },
        ]}
      />
    </div>
  );
}
