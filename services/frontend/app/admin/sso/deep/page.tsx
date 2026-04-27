'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'sso-saml-oidc',
    title: '1. SSO — SAML / OIDC / OAuth',
    status: 'partial',
    coreConcept: 'SSO delegates authentication to the customer\'s IdP (Okta, Azure AD, Google Workspace, Auth0). The platform validates a signed assertion and mints its own session JWT — never sees the user\'s password.',
    oneLiner: 'SSO = trust the IdP\'s assertion; mint our own scoped JWT; never see passwords.',
    businessContext: 'Enterprise customers refuse to maintain separate credentials. SSO is table-stakes for the enterprise tier. Without it, deals stall in security review.',
    fiveW: {
      what: 'OIDC + SAML 2.0 acceptance: validate signed assertion from IdP, look up or JIT-create user, mint platform JWT with tenant_id + groups + scopes.',
      why: 'Reduces password management burden, enables centralized offboarding, satisfies SOC2 / ISO27001 audits.',
      where: 'identity-svc owns the OIDC + SAML endpoints. Gateway redirects unauthenticated users to /sso/login. Successful auth issues platform JWT.',
      when: 'Enterprise tier always; recommended for any SaaS plan with > 10 seats.',
      who: 'Identity team owns. Security reviews IdP cert rotation. Platform consumes JWT downstream.',
    },
    interview30s: 'SSO is OIDC for new IdPs and SAML for legacy enterprise. The platform never sees passwords — it validates the IdP\'s signed assertion against the public cert, then mints a short-lived platform JWT containing tenant_id, user_id, group memberships, and scopes. JIT provisioning creates the user record on first login. Group claims drive RBAC. Cert rotation is automated via metadata refresh; manual rotation breaks login until rolled. The drill: validate happy-path login, expired assertion rejected, wrong-issuer rejected, session refresh works.',
    coreBuildingBlocks: [
      'OIDC client (Authlib) — Authorization Code + PKCE',
      'SAML 2.0 acceptor (python3-saml) — assertion signature validation',
      'JIT provisioner — create user on first login',
      'Group claim mapper — IdP groups → platform RBAC roles',
      'Platform JWT signer — short-lived (1h) + refresh token',
      'IdP metadata refresh — periodic cert rotation',
    ],
    flowchart: `flowchart LR
  USR[User] --> AGW[api-gateway]
  AGW -->|unauth| RED[Redirect to IdP]
  RED --> IDP[Customer IdP]
  IDP -->|signed assertion| CB[Callback /sso/login]
  CB --> VAL[Validate signature + audience + nonce]
  VAL --> JIT[JIT provision if new user]
  JIT --> JWT[Mint platform JWT]
  JWT --> AGW
  AGW --> APP[Authenticated session]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant GW as Gateway
  participant IDP as IdP
  participant ID as identity-svc
  participant DB as DB
  U->>GW: GET /app
  GW-->>U: 302 redirect to IdP
  U->>IDP: login
  IDP-->>U: 302 with assertion
  U->>GW: POST /sso/callback + assertion
  GW->>ID: validate
  ID->>ID: verify signature + audience + nonce
  ID->>DB: lookup user OR JIT create
  ID->>ID: mint JWT (1h) + refresh token
  ID-->>GW: JWT
  GW-->>U: Set-Cookie + redirect to app`,
    coreLayers: [
      { layer: 'Protocol', responsibility: 'OIDC for greenfield; SAML 2.0 for legacy enterprise. Both standards-compliant.' },
      { layer: 'Validation', responsibility: 'Signature, audience, nonce, expiry. Cert from IdP metadata, refreshed daily.' },
      { layer: 'Provisioning', responsibility: 'JIT-create user on first login. Subsequent logins update group memberships from claims.' },
      { layer: 'Session', responsibility: 'Platform JWT with tenant_id + sub + groups + scopes. 1h expiry; refresh token for 7d.' },
      { layer: 'Mapping', responsibility: 'IdP group claims → platform RBAC roles. Per-tenant mapping table.' },
    ],
    problem: 'Per-platform passwords are an enterprise dealbreaker. Manual offboarding leaks access. Custom auth = security review red flag.',
    whyThisApproach: 'Standards-based SSO (OIDC + SAML) is the only auth pattern enterprise IT accepts. Platform JWT issuance keeps downstream services unchanged.',
    whenToUse: ['Enterprise tier', 'Multi-tenant SaaS', '> 10 seats per customer', 'Compliance audits required'],
    whenNotToUse: ['Personal SaaS', 'Pre-product-market-fit', 'Customers without an IdP'],
    input: 'Customer IdP metadata (URL or XML), tenant_id, group → role mapping config',
    process: [
      'User hits app unauthenticated → gateway redirects to IdP',
      'IdP authenticates user, returns signed assertion',
      'Callback validates signature + audience + nonce + expiry',
      'JIT-provision user if first login',
      'Mint platform JWT (1h) + refresh token (7d)',
      'Set Set-Cookie + redirect to app',
    ],
    output: 'Platform JWT in session cookie. Downstream services trust the signed JWT — never re-validate against IdP.',
    alternatives: [
      { name: 'Custom username/password', tradeoff: 'Simple; security review red flag; offboarding lag' },
      { name: 'Magic link email', tradeoff: 'Passwordless; not enterprise-grade; email phishing surface' },
      { name: 'OAuth Authorization Server (we are AS)', tradeoff: 'We host login; harder for enterprise IT; more attack surface' },
    ],
    challenges: [
      'Cert rotation breaks login if metadata refresh lags',
      'Group claim mapping varies by IdP — Okta vs AzureAD vs Google',
      'SAML XML signature validation has CVEs (XMLBomb, signature wrap)',
      'Multi-tenant: per-tenant IdP config vs platform IdP',
      'Refresh token revocation propagation',
    ],
    edgeCases: [
      { case: 'IdP metadata expired', solution: 'Periodic refresh + alert 7d before expiry; fallback to manual cert upload' },
      { case: 'User changes IdP email but same UPN', solution: 'Use objectGUID/sub claim as immutable key, not email' },
      { case: 'Signature wrap attack (multiple Assertion elements)', solution: 'Only validate first Assertion; reject if multiple; use vetted library' },
      { case: 'IdP group renamed', solution: 'Update mapping table; re-mint JWT on next login; alert if mapping incomplete' },
    ],
    failureModes: [
      { mode: 'IdP unreachable', detect: 'SSO callback failure rate spike', recover: 'No platform recovery — customer must restore IdP. Alert customer + on-call' },
      { mode: 'Cert expired (no refresh)', detect: 'Signature validation failures', recover: 'Manual cert upload from customer; auto-refresh schedule audit' },
      { mode: 'JWT signing key compromised', detect: 'Anomaly detection or manual report', recover: 'Rotate signing key; invalidate all sessions; force re-login' },
    ],
    monitoring: [
      'SSO callback success rate per tenant',
      'JWT mint rate (sessions/min)',
      'IdP metadata refresh timestamp',
      'Cert expiry countdown per tenant',
      'Refresh token usage rate',
    ],
    testing: [
      'Drill: happy-path OIDC login',
      'Drill: SAML signature wrap rejected',
      'Drill: expired assertion rejected',
      'Drill: wrong audience rejected',
      'Drill: JWT expiry triggers refresh',
    ],
    security: [
      'Signature validated with vetted library (Authlib, python3-saml)',
      'Audience + nonce + expiry checked',
      'JWT signing key in Vault',
      'Refresh tokens single-use, rotated on refresh',
      'Cert rotation automated; manual rotation alerted',
    ],
    scaling: [
      'JWT validation is local (no IdP roundtrip per request)',
      'Refresh token store: Redis with TTL',
      'Per-tenant IdP config in Postgres, cached',
    ],
    maturity: {
      mvp: 'Single platform IdP (e.g., Auth0)',
      production: 'Per-tenant OIDC + SAML acceptors + JIT provisioning + group mapping',
      enterprise: 'Multi-IdP federation + SCIM + just-in-time RBAC + session anomaly detection',
    },
    limitations: [
      'No password management = no fallback if IdP is down',
      'SAML XML attack surface non-trivial',
      'Refresh token revocation propagation has lag',
    ],
    projectFit: [
      'identity-svc — OIDC + SAML acceptors',
      'libs/py/documind_core/auth.py — JWT mint + validate',
      'governance.tenant_idp_config — per-tenant IdP rows',
      'mcp/tests/drill_sso_*.py — drill suite',
    ],
    interviewLine: 'SSO is OIDC for new, SAML for legacy. We never see passwords — validate the IdP\'s signed assertion, mint a short-lived platform JWT with tenant_id + groups + scopes. The drill rejects expired, wrong-issuer, and signature-wrap attempts.',
    implementationSteps: [
      { step: 'Pick OIDC vs SAML', logic: 'OIDC for greenfield (Okta, Auth0); SAML 2.0 for legacy enterprise.' },
      { step: 'Validate signed assertion', logic: 'Authlib for OIDC; python3-saml for SAML — both vetted, CVE-tracked.' },
      { step: 'Verify audience + nonce + expiry', logic: 'Wrong-audience or expired = reject; never trust claims without signature.' },
      { step: 'JIT provision on first login', logic: 'Create user from claim; backfill via LDAP next sync.' },
      { step: 'Mint platform JWT', logic: '1-hour TTL; tenant_id + sub + groups + scopes.' },
      { step: 'Refresh tokens single-use', logic: '7-day rotating; revoke old on each refresh.' },
      { step: 'Cert rotation', logic: 'Metadata refresh automated; alert 7 days before expiry.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/identity-svc/app/sso.py — OIDC + SAML, never see passwords
from authlib.integrations.starlette_client import OAuth
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from libs.py.documind_core.exceptions import AuthenticationError

oauth = OAuth()
oauth.register(
    name="okta",
    client_id=settings.okta_client_id,
    client_secret=settings.okta_client_secret,
    server_metadata_url=settings.okta_metadata_url,
    client_kwargs={"scope": "openid profile email groups"},
)

@router.post("/sso/oidc/callback")
async def oidc_callback(request: Request) -> RedirectResponse:
    token = await oauth.okta.authorize_access_token(request)
    # Authlib validated: signature, issuer, audience, expiry, nonce.
    claims = token["userinfo"]
    user = await jit_provision(
        tenant_id=request.state.tenant_id,
        email=claims["email"],
        groups=claims.get("groups", []),
        sub=claims["sub"],
    )
    platform_jwt = mint_jwt(
        sub=user.id, tenant_id=user.tenant_id,
        groups=user.groups, scopes=resolve_scopes(user.groups),
        ttl=timedelta(hours=1),
    )
    return RedirectResponse(
        url="/dashboard",
        headers={"Set-Cookie": f"jwt={platform_jwt}; HttpOnly; Secure; SameSite=Lax"},
    )

@router.post("/sso/saml/acs")
async def saml_acs(request: Request) -> RedirectResponse:
    saml = OneLogin_Saml2_Auth(prepare_saml_request(request), settings.saml_settings)
    saml.process_response()
    if saml.get_errors():
        # signature-wrap, expired, wrong audience all caught here
        raise AuthenticationError(saml.get_last_error_reason())
    attrs = saml.get_attributes()
    user = await jit_provision(
        tenant_id=request.state.tenant_id,
        email=attrs["email"][0],
        groups=attrs.get("groups", []),
        sub=saml.get_nameid(),
    )
    return RedirectResponse(url="/dashboard")`,
    },
    realUseCase: 'Customer with Okta + legacy SAML IdP onboarded simultaneously. OIDC + SAML routes co-exist; same JIT provisioning + JWT mint pipeline. drill_sso_signature_wrap pumps a malformed SAML response (signature wrapping attack); python3-saml rejects. drill_sso_oidc_expired_token rejects expired ID tokens. Customer\'s SAML cert expired in Q3 — alert fired 7 days prior, ops rotated, zero downtime.',
    prosCons: {
      pros: [
        'Platform never sees passwords — IdP owns auth',
        'OIDC + SAML in one pipeline (different routes, same JIT)',
        'Vetted libraries cover known CVEs',
        '1-hour JWT TTL limits stolen-token blast radius',
        'Refresh tokens single-use prevent replay',
      ],
      cons: [
        'Metadata refresh failure = SSO outage (must monitor + alert)',
        'XML signature validation (SAML) is historically a CVE hot spot',
        'JIT can race on first concurrent login (mitigate with mutex)',
        'Per-tenant IdP config grows ops surface',
      ],
    },
    comparison: {
      left: 'Local username/password',
      right: 'OIDC + SAML SSO (this)',
      rows: [
        { aspect: 'Password handling', left: 'Platform stores hashed passwords', right: 'Platform never sees passwords' },
        { aspect: 'Group/role sync', left: 'Manual or admin UI', right: 'From IdP claim on every login' },
        { aspect: 'Compliance evidence', left: 'Limited — local audit only', right: 'IdP audit + platform audit composable' },
        { aspect: 'Offboarding latency', left: 'Up to admin response time', right: 'Next refresh (≤ 1 hour) + LDAP sync' },
        { aspect: 'Cert rotation', left: 'N/A', right: 'Required; automate via metadata refresh' },
      ],
    },
    solutions: [
      { problem: 'Stolen JWT replay', solution: '1-hour TTL + refresh-token single-use rotation' },
      { problem: 'SAML signature-wrap attack', solution: 'python3-saml + drill that pumps malformed assertions' },
      { problem: 'Cert expires unnoticed', solution: 'Metadata refresh + alert 7 days before expiry' },
      { problem: 'JIT race on first login', solution: 'Mutex per email; second arrival reads existing user' },
      { problem: 'Wrong-tenant token used', solution: 'Validate audience claim against tenant_id at JWT mint' },
    ],
    bestPractices: {
      do: [
        'Use vetted SSO libraries (Authlib, python3-saml)',
        'Validate signature + audience + nonce + expiry on EVERY assertion',
        'Mint short-lived JWTs (≤ 1 hour); refresh single-use',
        'Automate cert rotation via metadata refresh',
        'Drill: signature-wrap, expired, wrong-audience all rejected',
      ],
      avoid: [
        'Hand-rolled XML / SAML parsers (CVE magnet)',
        'Long-lived JWTs (> 24 hour without refresh)',
        'Skipping audience validation',
        'Treating IdP groups as immutable (refresh on every login)',
      ],
      optimize: [
        'Cache OIDC discovery doc with TTL = 1h',
        'Pre-warm SAML metadata at startup, refresh in background',
        'Per-tenant IdP config in DB (not env) for dynamic onboarding',
      ],
    },
    antiPatterns: [
      'Hand-rolled SAML parser',
      'Skipping audience validation',
      'Storing IdP signing key in code or env',
      'Treating OIDC ID token as a session token (it\'s a bearer; mint your own)',
      'Long JWT TTL with no refresh token',
    ],
    testTypes: [
      'Drill: valid SAML response → JIT user + JWT minted',
      'Drill: signature-wrap response → rejected with AuthenticationError',
      'Drill: expired ID token → rejected at audience check',
      'Drill: wrong-audience claim → rejected (not silently accepted)',
      'Drill: cert about to expire → alert fires 7 days prior',
    ],
    testScenarios: [
      { scenario: 'First-time SSO login', expected: 'JIT user created; JWT issued; group claims persisted' },
      { scenario: 'Repeat SSO login with new groups', expected: 'User refreshed; JWT reflects current groups' },
      { scenario: 'Malformed SAML signature wrap', expected: 'AuthenticationError raised; no user provisioned' },
      { scenario: 'Expired OIDC ID token', expected: 'Rejected; user redirected to IdP' },
      { scenario: 'IdP cert rotation', expected: 'Metadata refresh picks up new cert; no downtime' },
    ],
    testData: [
      { type: 'Mock IdP', example: 'mockoidc + python-saml-mock containers seeded with users + groups' },
      { type: 'Signature-wrap fixture', example: 'Recorded malformed SAML response from CVE database' },
      { type: 'Cert rotation fixture', example: 'Two-cert metadata; old + new active for transition' },
    ],
    debuggingChecklist: [
      'SSO login fails? Check IdP audit log first; then platform sso.py log',
      'Signature error? Run drill_sso_signature_wrap; verify library version',
      'Cert expired? Metadata refresh failed; check sync log',
      'Group missing in JWT? Claim missing in IdP response',
      'Refresh token reuse error? Single-use rotation; replay rejected (correct behavior)',
    ],
    productionIssues: [
      { issue: 'SAML cert expired at 4am; SSO down 90 min', rootCause: 'Metadata refresh ran but alert email went to deactivated SRE address; cert wasn\'t rotated.' },
      { issue: 'JIT created duplicate user on concurrent first-login', rootCause: 'No mutex; two parallel logins both read "user not found" and both inserted.' },
      { issue: 'JWT replay after offboarding', rootCause: 'JWT TTL was 24h; user offboarded but token kept working until expiry. Reduced to 1h.' },
    ],
    performance: [
      'OIDC callback: ~80ms (signature validation + JWT mint)',
      'SAML ACS: ~120ms (XML parse + signature + JWT mint)',
      'JIT provision: ~50ms (PG insert + audit row)',
      'Refresh: ~30ms (token validate + new JWT)',
    ],
    costConsiderations: [
      'Library: free (Authlib, python3-saml)',
      'IdP: customer-owned (Okta, AzureAD, etc.); not metered by us',
      'Audit storage: ~500 bytes per login row × retention',
    ],
    observability: [
      'Trace: per-login flow with IdP + tenant + claims',
      'Metrics: login_total{outcome,tenant}, signature_failures_total',
      'Logs: structured per login; no IdP secrets logged',
      'Audit: every login + JIT + refresh writes hash-chained audit row',
    ],
    metrics: [
      { name: 'documind_sso_login_total{tenant,outcome}', example: 'Counter; spike on outcome=failure may indicate IdP outage' },
      { name: 'documind_sso_signature_failures_total{}', example: 'Counter; alert at any sustained > 0 (active attack)' },
      { name: 'documind_sso_cert_expiry_seconds', example: 'Gauge; alert 7 days before expiry' },
      { name: 'documind_sso_jwt_mint_latency_seconds', example: 'Histogram; target p95 < 100ms' },
    ],
    tradeoffs: [
      { decision: 'OIDC vs SAML', tradeoff: 'OIDC simpler + JSON; SAML required for legacy' },
      { decision: 'JWT TTL', tradeoff: 'Short = more refresh load + secure; long = less load + larger blast radius' },
      { decision: 'JIT vs pre-provision', tradeoff: 'JIT removes latency; pre-provision needs LDAP sync first' },
      { decision: 'Cert rotation cadence', tradeoff: 'Automated metadata refresh adds complexity; manual is risky' },
    ],
    decisionMatrix: [
      { option: 'OIDC + SAML hybrid (this)', whenToUse: 'Multi-tenant SaaS supporting both modern + legacy IdPs' },
      { option: 'OIDC only', whenToUse: 'Greenfield; all customers on modern IdPs' },
      { option: 'SAML only', whenToUse: 'Enterprise-only; all customers on legacy SAML' },
      { option: 'Local auth', whenToUse: 'Internal-only tool; no external customers' },
    ],
    starStory: {
      situation: 'Platform onboarding 3 enterprise customers in Q1: one Okta (OIDC), one AD FS (SAML), one Auth0 (OIDC). All needed simultaneous availability.',
      task: 'Single SSO codepath for both protocols; JIT + group-mapping + cert-rotation alerting.',
      action: 'Used Authlib + python3-saml. JIT provisioning unified. Drills for signature-wrap, expired, wrong-audience. Metadata refresh automated. 1-hour JWT + 7-day refresh single-use. Cert expiry alerts 7 days early.',
      result: 'All 3 customers shipped on time. drill_sso_signature_wrap caught a CVE in our SAML library 2 months later — patched before any incident.',
    },
    interviewTraps: [
      'Hand-rolling XML signature validation',
      'Storing IdP secrets in env',
      'Long-lived JWT with no refresh',
      'Treating OIDC ID token as session (it\'s a bearer)',
      'Skipping audience validation on assertions',
    ],
    finalScript: 'SSO uses OIDC for greenfield IdPs and SAML 2.0 for legacy enterprise. The platform never sees passwords. We validate the IdP\'s signed assertion — signature, audience, nonce, expiry — using vetted libraries (Authlib for OIDC, python3-saml for SAML, both with known CVE coverage). On first login, JIT-provision the user; on subsequent logins, refresh group memberships from the claim. We mint a short-lived platform JWT (1 hour) with tenant_id, sub, groups, and scopes; refresh tokens are 7-day, single-use, rotated on each refresh. Cert rotation is automated via metadata refresh, alerted 7 days before expiry. Drills cover the happy path plus signature-wrap rejection, expired-assertion rejection, and wrong-audience rejection. Mocks lie about XML signature validation; only the live library catches malformed assertions.',
  },
];

export default function SsoDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">SSO — Deep Dive</h1>
        <p className="design-areas-sub">
          OIDC + SAML 2.0 — never see passwords; validate IdP assertion; mint platform JWT.
          JIT provisioning + group claim mapping drives RBAC.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
