'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'ldap-enterprise-identity',
    title: '1. LDAP — enterprise identity sync',
    status: 'partial',
    coreConcept: 'LDAP synchronization pulls user + group state from corporate directories (Active Directory, FreeIPA, OpenLDAP) into the platform\'s identity service. Periodic sync + just-in-time provisioning are the two patterns.',
    oneLiner: 'LDAP = corporate directory as source of truth; platform identity = projection.',
    businessContext: 'Enterprise customers require user lifecycle automation — when HR offboards, the user loses access in minutes, not days. LDAP sync is the standard mechanism.',
    fiveW: {
      what: 'A scheduled job + on-demand resolver that pulls users + groups from LDAP and projects them into platform identity tables.',
      why: 'Manual user management at enterprise scale is impossible. SSO alone authenticates but doesn\'t handle group memberships or offboarding lag.',
      where: 'identity-svc runs the sync job. Reads via ldap3 client. Writes to identity.users + identity.group_memberships in Postgres.',
      when: 'Enterprise tier customers; usually with on-prem AD or hybrid Azure AD.',
      who: 'Identity team owns. Customer IT admins manage source AD. Compliance audits sync events.',
    },
    interview30s: 'For enterprise identity, we sync from LDAP every 15 minutes for users + groups, plus on-demand resolution for fresh-signup users via just-in-time provisioning. Sync writes to identity tables in Postgres with a tombstone column for offboarded users — never hard-delete because audit logs need historical username resolution. Group memberships drive RBAC at the policy layer. The drill: spawn a fake LDAP, add user, verify sync; remove user, verify tombstone; check that policy denies after offboarding.',
    coreBuildingBlocks: [
      'LDAP client (ldap3 Python) with TLS + bind credentials',
      'Sync scheduler — APScheduler or Celery beat at 15min interval',
      'JIT provisioning hook — on first SSO login, fetch + create user',
      'identity.users table — soft-delete via tombstone',
      'identity.group_memberships — many-to-many; FK with ON DELETE RESTRICT',
      'Audit chain — every sync event logged',
    ],
    flowchart: `flowchart LR
  AD[(Active Directory)] -->|LDAP TLS| SYNC[Sync job]
  SYNC --> DIFF[Diff vs current state]
  DIFF -->|new| INS[INSERT user + groups]
  DIFF -->|changed| UPD[UPDATE user + groups]
  DIFF -->|deleted| TOMB[Tombstone user]
  INS --> AUD[audit_log]
  UPD --> AUD
  TOMB --> AUD
  AUD --> PG[(identity tables)]`,
    sequence: `sequenceDiagram
  autonumber
  participant Sched as Scheduler
  participant LDAP as LDAP
  participant Sync as Sync job
  participant DB as identity DB
  Sched->>Sync: tick (15min)
  Sync->>LDAP: bind + search users
  LDAP-->>Sync: user list + groups
  Sync->>DB: SELECT current state
  DB-->>Sync: rows
  Sync->>Sync: diff
  Sync->>DB: BEGIN tx
  Sync->>DB: UPSERT users
  Sync->>DB: tombstone offboarded
  Sync->>DB: audit row per change
  Sync->>DB: COMMIT`,
    coreLayers: [
      { layer: 'Source', responsibility: 'AD / FreeIPA / OpenLDAP. Customer-managed; we read-only.' },
      { layer: 'Client', responsibility: 'ldap3 with TLS, bind credentials in Vault / AWS Secrets.' },
      { layer: 'Diff', responsibility: 'Compare LDAP state vs DB; classify add/update/tombstone.' },
      { layer: 'Persistence', responsibility: 'identity.users (tombstone-aware), identity.group_memberships, identity.audit.' },
      { layer: 'JIT', responsibility: 'On first SSO login, fetch user from LDAP synchronously if not in DB.' },
    ],
    problem: 'Manual user lifecycle = stale access + audit gaps. SSO alone authenticates but doesn\'t synchronize group state. LDAP is the enterprise-standard mechanism.',
    whyThisApproach: 'Pull-based sync is simpler than push (customer doesn\'t need to expose webhooks). 15-minute cadence is enterprise-acceptable. Tombstone preserves audit trail.',
    whenToUse: ['Enterprise tier', 'On-prem AD environments', 'Compliance requires offboarding within hours'],
    whenNotToUse: ['SaaS-only customers without AD', 'Greenfield startups with no IdP', 'Cross-region performance issues with LDAP'],
    input: 'LDAP bind config (DN, credentials, base DN, filters) + tenant_id',
    process: [
      'Bind to LDAP with TLS',
      'Search users + groups under base DN',
      'Diff against current identity DB state',
      'Apply changes in single transaction',
      'Log audit rows for every change',
    ],
    output: 'identity.users + identity.group_memberships consistent with LDAP within 15 minutes of source change.',
    alternatives: [
      { name: 'SCIM (push from IdP)', tradeoff: 'Real-time; requires customer to configure SCIM endpoint; more setup' },
      { name: 'Just-in-time only (no sync)', tradeoff: 'Lazy; group memberships stale until login; offboarding lag' },
      { name: 'Manual UI', tradeoff: 'Simple; doesn\'t scale; audit-poor' },
    ],
    challenges: [
      'LDAP schemas vary across vendors',
      'Bind credential rotation often manual',
      'Group nesting depth varies; recursive resolution expensive',
      'Customer AD outages break sync',
      'Privacy: not all LDAP attributes safe to project',
    ],
    edgeCases: [
      { case: 'LDAP unreachable mid-sync', solution: 'Roll back transaction; alert; retry with exponential backoff' },
      { case: 'User deleted from LDAP but has live sessions', solution: 'Tombstone in DB; gateway revokes session within 60s via Redis pub/sub' },
      { case: 'Customer renames user (DN change)', solution: 'Use immutable objectGUID/objectSid as identity key, not DN' },
      { case: 'Bind credentials expired', solution: 'Vault-managed rotation; alert 30d before expiry' },
    ],
    failureModes: [
      { mode: 'Sync stalls (LDAP unreachable)', detect: 'Last successful sync timestamp > 1h old', recover: 'Page on-call; verify LDAP connectivity; manual sync if needed' },
      { mode: 'Bind credentials expired', detect: 'Auth failures in sync logs', recover: 'Rotate via Vault; restart sync' },
      { mode: 'Schema mismatch', detect: 'Sync errors on specific attribute mapping', recover: 'Update mapper; deploy' },
    ],
    monitoring: [
      'Last successful sync timestamp per tenant',
      'Sync duration p95',
      'Diff size (changes per sync)',
      'Tombstone count per day',
      'Bind auth failures',
    ],
    testing: [
      'Drill: spawn fake LDAP; add/remove user; verify sync',
      'Drill: tombstone propagates to RBAC denial',
      'Drill: bind credential rotation without downtime',
    ],
    security: [
      'TLS-only LDAP connections',
      'Bind credentials in Vault, rotated quarterly',
      'Per-tenant audit chain on identity changes',
      'No PII in logs (DN-only references)',
    ],
    scaling: [
      'Linear in user count up to ~100K per tenant',
      'Beyond: parallelize per-OU; checkpoint progress',
      'JIT provisioning offloads first-time login',
    ],
    maturity: {
      mvp: 'Manual sync via admin script',
      production: 'Scheduled sync + JIT + audit chain',
      enterprise: 'Multi-AD federation + SCIM fallback + change webhooks',
    },
    limitations: [
      'Pull-based sync has 15-minute lag',
      'Group nesting deep = expensive recursion',
      'Cross-domain trust complex',
    ],
    projectFit: [
      'identity-svc — owns LDAP sync + JIT',
      'identity.users + identity.group_memberships — projection',
      'mcp/tests/drill_ldap_sync.py — sync drill',
    ],
    interviewLine: 'LDAP sync is pull-based, 15-minute cadence, tombstone-aware. Group memberships drive RBAC. The non-negotiable test is a drill that adds + removes a user in fake LDAP and verifies platform state converges within one cycle.',
    finalScript: 'For enterprise identity, we sync from LDAP every 15 minutes — users plus group memberships — and additionally do just-in-time provisioning on first SSO login. Sync uses an immutable objectGUID as the identity key, not the DN — DNs change when customers reorganize OUs. Tombstone-on-delete preserves audit trail; we never hard-delete a user because historical audit_log rows need username resolution. Bind credentials are Vault-rotated quarterly. The drill spawns a fake LDAP, adds and removes users, and verifies platform state converges within one sync cycle. RBAC denial fires within 60 seconds of tombstone via Redis pub/sub.',
  },
];

export default function LdapDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">LDAP — Deep Dive</h1>
        <p className="design-areas-sub">
          Enterprise identity sync — pull-based, 15-min cadence, tombstone-aware. Drives
          RBAC group memberships into the platform.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
