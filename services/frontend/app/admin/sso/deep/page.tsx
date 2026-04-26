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
