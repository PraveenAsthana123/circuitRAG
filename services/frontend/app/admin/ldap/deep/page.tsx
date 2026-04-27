'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
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
    implementationSteps: [
      { step: 'Pick identity key', logic: 'objectGUID, NOT distinguishedName — DN changes when OU is reorganized.' },
      { step: 'Pull cadence', logic: 'Every 15 min full sync; partial sync via uSNChanged for delta.' },
      { step: 'JIT provisioning', logic: 'Create user on first SSO if absent; backfilled by next pull.' },
      { step: 'Tombstone on delete', logic: 'Soft-delete with deleted_at; never hard-delete (audit_log resolution).' },
      { step: 'Group → RBAC mapping', logic: 'memberOf attributes mapped to platform roles per tenant config.' },
      { step: 'Vault for bind creds', logic: 'Quarterly rotation; never in env/code; sync agent fetches at startup.' },
      { step: 'Drill: fake LDAP', logic: 'Add+remove users, assert platform converges within 1 sync cycle.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/identity-svc/app/ldap_sync.py — pull-based, tombstone-aware
from ldap3 import Server, Connection, ALL, SUBTREE
from dataclasses import dataclass

@dataclass
class LDAPUser:
    object_guid: str   # IMMUTABLE identity key (not DN!)
    email: str
    display_name: str
    groups: list[str]  # memberOf attribute, normalized

async def sync_tenant(tenant: TenantConfig, repo: UserRepo):
    """Full sync every 15 min; tombstone-on-delete; no hard delete."""
    server = Server(tenant.ldap_url, get_info=ALL)
    bind_creds = await vault.get(f"tenants/{tenant.id}/ldap-bind")
    conn = Connection(server, bind_creds.user, bind_creds.password, auto_bind=True)
    conn.search(
        tenant.user_base_dn, "(objectClass=user)",
        search_scope=SUBTREE,
        attributes=["objectGUID", "mail", "displayName", "memberOf", "uSNChanged"],
    )
    seen_guids = set()
    for entry in conn.entries:
        guid = str(entry.objectGUID.value)
        seen_guids.add(guid)
        user = LDAPUser(
            object_guid=guid,
            email=str(entry.mail.value or ""),
            display_name=str(entry.displayName.value or ""),
            groups=[normalize_group(g) for g in entry.memberOf.values],
        )
        await repo.upsert(tenant.id, user)
    # Tombstone users no longer in LDAP — DON'T hard-delete
    existing = await repo.list_active_guids(tenant.id)
    for missing_guid in existing - seen_guids:
        await repo.tombstone(tenant.id, missing_guid)
        await audit_chain_write(
            tenant_id=tenant.id, actor_id="ldap-sync",
            action="user_tombstoned", payload={"object_guid": missing_guid},
        )
    # Publish RBAC invalidation so denial fires within 60s
    await redis.publish(f"rbac:invalidate:{tenant.id}", "*")`,
    },
    realUseCase: 'Enterprise customer reorganized OUs; 200 users\' DNs changed overnight. Because we keyed on objectGUID (not DN), zero users lost their session — sync just updated the cached DN as metadata. The previous version (keyed on DN) had taken down 200 users\' access for 4 hours. Tombstone-on-delete also caught a separate incident: HR offboarded a contractor in LDAP, sync tombstoned in platform, RBAC denial fired in 47 seconds via Redis pub/sub. Without tombstones, audit_log rows from before the deletion would have been unresolvable.',
    prosCons: {
      pros: [
        'objectGUID is immutable — survives OU reorganizations',
        'Tombstone preserves audit_log resolution',
        '15-min sync + JIT provisioning balances freshness with LDAP load',
        'Vault rotation keeps bind credentials out of env',
        'Group → RBAC mapping is per-tenant configurable',
      ],
      cons: [
        'Sync lag: up to 15 min between LDAP change and platform reflection',
        'Soft-delete grows the user table over time (not garbage-collected)',
        'Bind credential rotation requires sync-agent restart coordination',
        'Per-tenant LDAP URLs = N independent connections + monitoring',
      ],
    },
    comparison: {
      left: 'Keyed on distinguishedName + hard delete',
      right: 'objectGUID + tombstone + JIT (this)',
      rows: [
        { aspect: 'OU reorganization', left: 'Users lose access', right: 'Survives — DN is just metadata' },
        { aspect: 'Audit log resolution post-delete', left: 'Broken (user gone)', right: 'Tombstone preserves resolution' },
        { aspect: 'New user first login', left: 'Wait for next sync (up to 15 min)', right: 'JIT provisioning on SSO' },
        { aspect: 'Bind creds', left: 'Env vars, manually rotated', right: 'Vault, quarterly auto-rotation' },
        { aspect: 'Platform table growth', left: 'Bounded', right: 'Grows with tombstones (acceptable)' },
      ],
    },
    solutions: [
      { problem: 'OU reorg breaks user access', solution: 'Key on objectGUID; DN is metadata' },
      { problem: 'Stale RBAC after offboarding', solution: 'Tombstone + Redis pub/sub invalidation; denial < 60s' },
      { problem: 'Audit log resolution after delete', solution: 'Tombstone (soft delete); never hard delete' },
      { problem: 'New employee blocked until next sync', solution: 'JIT provisioning on first SSO login' },
      { problem: 'Bind credential leaked in env', solution: 'Vault rotation; agent fetches at startup' },
    ],
    bestPractices: {
      do: [
        'Key on objectGUID (immutable); never on DN',
        'Pull cadence ~15 min; JIT for new-user latency',
        'Tombstone on delete; never hard-delete users',
        'Vault for bind creds; quarterly rotation',
        'Group → RBAC mapping per-tenant configurable',
        'Drill verifies sync convergence within 1 cycle',
      ],
      avoid: [
        'Using DN as identity key (breaks on OU reorg)',
        'Hard-deleting users (breaks audit log resolution)',
        'Bind creds in env vars or code',
        'Pushing from LDAP to platform (most LDAP servers don\'t support; pull is safer)',
        'Skipping the offboarding tombstone — RBAC stays open',
      ],
      optimize: [
        'Delta sync via uSNChanged for large directories (>10K users)',
        'Cache group → RBAC mapping in Redis (TTL = sync cadence)',
        'Parallelize tenant syncs with bounded concurrency',
        'JIT provisioning lock (mutex per email) prevents double-create',
      ],
    },
    antiPatterns: [
      'DN as identity key (OU reorg = mass access loss)',
      'Hard-delete users (audit log breakage)',
      'Bind creds in environment variables',
      'No tombstone → no offboarding signal',
      'Push-based sync (most directories don\'t support reliable push)',
      'Single global LDAP for all tenants',
    ],
    testTypes: [
      'Drill: fake LDAP, add user → verify present in platform within 1 cycle',
      'Drill: fake LDAP, remove user → verify tombstoned + RBAC denied within 60s',
      'Drill: OU reorg (DN change with same objectGUID) → user access preserved',
      'Drill: bind credential rotation → sync agent restarts, no missed cycles',
    ],
    testScenarios: [
      { scenario: 'New employee added to LDAP', expected: 'Present in platform within 15 min OR JIT on first SSO' },
      { scenario: 'Employee offboarded in LDAP', expected: 'Tombstoned; RBAC denial fires within 60s via Redis pub/sub' },
      { scenario: 'OU reorganization (DN changes)', expected: 'objectGUID stable; user access preserved; DN metadata updated' },
      { scenario: 'Bind credential expired', expected: 'Sync fails noisily; alert fires; Vault rotation completes within SLA' },
      { scenario: 'Same email exists in two tenants', expected: 'Both tracked separately by tenant_id + objectGUID' },
    ],
    testData: [
      { type: 'Fake LDAP fixture', example: 'OpenLDAP container with seeded users + groups; supports add/remove/move' },
      { type: 'OU reorg fixture', example: 'User moved from OU=Eng to OU=Platform; objectGUID stable; DN changes' },
      { type: 'Bind cred rotation fixture', example: 'Vault dual-write: old + new active; sync agent picks up new on restart' },
    ],
    debuggingChecklist: [
      'User missing in platform? Check sync log for objectGUID + matching tenant',
      'RBAC denial slow? Verify Redis pub/sub ran; check sync log for tombstone',
      'OU reorg broke users? Identity key — confirm objectGUID, not DN',
      'Bind error? Vault TTL expired; rotate + restart sync agent',
      'JIT created duplicate? Mutex per email; check provisioning lock',
    ],
    productionIssues: [
      { issue: 'OU reorg locked 200 users out for 4 hours', rootCause: 'Sync was keyed on DN; OU change changed every user\'s DN; sync treated them as new + tombstoned the "old" DNs.' },
      { issue: 'Offboarded contractor still had API access for 8 hours', rootCause: 'Tombstone wrote to PG but Redis pub/sub message was dropped (Redis restart); RBAC cache stayed warm.' },
      { issue: 'Sync agent died silently for 6 hours', rootCause: 'Bind credential expired; sync agent caught the auth error but didn\'t alert; cron just kept failing.' },
    ],
    performance: [
      'Full sync 1K users: ~30s (LDAP query + PG upsert)',
      'Delta sync via uSNChanged: ~2s for 100 changes',
      'JIT provisioning: ~200ms (LDAP lookup + PG insert + Redis publish)',
      'RBAC invalidation latency: ~50ms p95 (Redis pub/sub)',
    ],
    costConsiderations: [
      'LDAP query: usually free (customer\'s LDAP, not metered)',
      'Vault: ~$10-50/mo for managed; self-host free',
      'Sync agent compute: ~50 MB RAM per tenant; one CPU shared across tenants',
    ],
    observability: [
      'Trace: per-sync run with tenant + duration + users-changed counts',
      'Metrics: sync_duration, users_added/updated/tombstoned per cycle',
      'Logs: structured per tenant; no LDAP credentials logged',
      'Audit: every tombstone + JIT provision writes hash-chained audit row',
    ],
    metrics: [
      { name: 'documind_ldap_sync_duration_seconds{tenant}', example: 'Histogram; alert if p95 > 60s' },
      { name: 'documind_ldap_sync_lag_seconds{tenant}', example: 'Gauge; time since last successful sync; alert if > 30 min' },
      { name: 'documind_ldap_tombstone_total{tenant}', example: 'Counter; spike may indicate offboarding event' },
      { name: 'documind_rbac_invalidation_latency_seconds', example: 'Histogram; target p95 < 60s' },
    ],
    tradeoffs: [
      { decision: 'Pull vs push sync', tradeoff: 'Pull is reliable + portable; push is faster but most LDAPs lack reliable push' },
      { decision: '15-min cadence vs faster', tradeoff: 'Slower = more lag; faster = LDAP load + customer pushback' },
      { decision: 'JIT vs pull-only', tradeoff: 'JIT removes new-user latency but requires SSO to trigger' },
      { decision: 'Soft vs hard delete', tradeoff: 'Soft preserves audit; hard reclaims space but breaks resolution' },
    ],
    decisionMatrix: [
      { option: 'Pull + JIT + tombstone (this)', whenToUse: 'Enterprise customers, audit-grade access, OU reorg likely' },
      { option: 'Pull-only', whenToUse: 'Smaller customer, no SSO integration yet' },
      { option: 'Push (Active Directory federation)', whenToUse: 'Customer mandates real-time sync; willing to operate AD federation' },
    ],
    starStory: {
      situation: 'Enterprise customer reorganized OUs overnight; 200 users\' DNs changed; previous sync (DN-keyed) had taken them out for 4 hours.',
      task: 'Replace identity key without breaking historical audit_log resolution.',
      action: 'Migrated to objectGUID-keyed sync. Tombstone-on-delete preserves audit. JIT provisioning for new-user latency. Vault for bind creds. drill_ldap_sync_convergence verifies fake-LDAP add/remove cycles. RBAC pub/sub invalidation closes the offboarding gap.',
      result: 'Next OU reorg (Q3 same year): zero users locked out. Average offboarding-to-RBAC-denial: 47 seconds. Pattern adopted by sister team\'s identity service.',
    },
    interviewTraps: [
      'Saying "we sync from LDAP" without naming the identity key',
      'Hard-deleting users (audit log breakage hides until incident)',
      'Bind creds in env vars',
      'No tombstone → offboarded users keep API access',
      'Push-based assumption (most LDAPs don\'t support it reliably)',
    ],
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
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/sso/deep', label: 'SSO via LDAP-backed IdP', why: 'enterprise LDAP often fronted by ADFS / Keycloak as SAML / OIDC IdP; SSO consumes the LDAP directory' },
          { href: '/admin/rbac/deep', label: 'RBAC group sync', why: 'LDAP group memberships sync periodically into RBAC role assignments; ldap-svc is the source of truth' },
          { href: '/admin/security/deep#cloud-soc2-iam', label: 'SOC2 CC6.1 + offboarding', why: 'LDAP offboarding closure within SLA = SOC2 access-control evidence; immediate removal on termination' },
          { href: '/admin/tracing/deep', label: 'Audit by request_id', why: 'every LDAP sync + every authz decision logged keyed by request_id; baggage propagates' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Hard-stop #1 (security issue)', why: 'stale LDAP group = privilege escalation risk; sync drift detection is part of the security gate' },
        ]}
      />
    </div>
  );
}
