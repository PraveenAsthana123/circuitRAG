'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'operations-runbooks',
    title: '1. Operations runbooks (canonical incident + lifecycle catalog)',
    status: 'shipped',
    coreConcept: 'A canonical catalog of operational runbooks under docs/runbooks/. Each runbook has a single owner, a clear trigger condition (when to read), step-by-step actions, and a verification step. Runbooks land in repo (versioned, reviewable) — not in a wiki that drifts.',
    problem: 'Operational knowledge accretes in Slack threads, individual heads, and stale wiki pages. When an incident strikes at 3am, the on-call engineer cannot find the recovery procedure; even when they find it, half the steps are out of date. Runbooks-in-repo solves the freshness problem; canonical catalog solves the discoverability problem.',
    whyThisApproach: 'Runbook = markdown file in docs/runbooks/. Versioned in git; reviewed in PRs; verifiable against current code. Catalog index is part of /admin so operators query the catalog instead of asking Slack. Per global §47 each release ships an updated runbook + on-call rotation.',
    whenToUse: ['Production incidents (DR_RUNBOOK, INCIDENT_RESPONSE)', 'Recurring operational tasks (ai-cache-migration, alertmanager-webhook setup)', 'Onboarding (autonomous-loop-cheatsheet)', 'Per-domain debugging (genai-rag-failure-scenarios)'],
    whenNotToUse: ['One-shot decisions (use ADRs)', 'Architectural rationale (use ADRs / C4 / JAD)', 'Ephemeral session notes (use git log / commit messages)'],
    input: 'incident or task trigger + on-call operator + access to repo',
    process: [
      'Trigger fires (alert, pager, scheduled task)',
      'Operator opens /admin/ops-fabric or runs `ls docs/runbooks/`',
      'Catalog shows trigger → runbook map',
      'Operator opens the runbook, reads steps',
      'Steps execute against current code (verifiable)',
      'Verification step confirms outcome; failure path documented',
      'Post-incident: runbook updated with what was learned',
    ],
    output: 'Successful operation + updated runbook reflecting reality.',
    flowchart: `flowchart LR
  trig[Trigger] --> cat[Catalog lookup]
  cat --> rb[Runbook MD]
  rb --> steps[Steps]
  steps --> verify[Verify step]
  verify -->|pass| done[Done]
  verify -->|fail| rec[Recovery path]
  rec --> esc[Escalate or update runbook]`,
    sequence: `sequenceDiagram
  autonumber
  participant T as Trigger
  participant Op as On-call
  participant R as Runbook
  participant S as Step
  participant V as Verifier
  T->>Op: alert
  Op->>R: open per catalog
  loop each step
    Op->>S: execute
    S->>V: verify
    V-->>Op: pass / fail
  end
  alt all pass
    Op-->>T: resolved
  else step fails
    Op->>R: update runbook
    Op->>Op: escalate
  end`,
    alternatives: [
      { name: 'Wiki-only documentation', tradeoff: 'Drifts; not reviewed; not greppable from code' },
      { name: 'Tribal knowledge / Slack', tradeoff: 'Lost on attrition; no audit trail; new on-call has nothing' },
      { name: 'Auto-generated from code', tradeoff: 'Always fresh; cannot capture WHY; useful as supplement only' },
    ],
    challenges: [
      'Runbook freshness (review cadence)',
      'Trigger-to-runbook map maintenance',
      'Step verification (executable steps vs prose)',
      'Discoverability (catalog page vs ls docs/runbooks)',
    ],
    edgeCases: [
      { case: 'Multi-runbook incident (cache + alert)', solution: 'Catalog shows trigger → runbook(s); compose-with footer per runbook' },
      { case: 'Runbook step depends on something deprecated', solution: 'Quarterly review; deprecated runbook moved to archive/; replacement linked' },
      { case: 'Runbook proposes a §42-gated action', solution: 'Step explicitly says "operator confirmation required"; never bypass' },
    ],
    failureModes: [
      { mode: 'Runbook not run (operator can\'t find)', detect: 'Slack incident reconstructed without runbook reference', recover: 'Catalog UI improvement; trigger-to-runbook map' },
      { mode: 'Runbook step out of date', detect: 'Step fails verification; manual workaround documented', recover: 'Update runbook in same PR as bugfix' },
      { mode: 'Runbook ownership unclear', detect: 'Last-edit blame from a now-departed engineer', recover: 'CODEOWNERS for docs/runbooks/; explicit owner in frontmatter' },
    ],
    monitoring: [
      'documind_runbook_runs_total (per runbook)',
      'documind_runbook_last_review_age_days',
      '/admin/ops-fabric runbook catalog page',
    ],
    testing: [
      'drill_runbook_catalog_freshness (PLANNED — every runbook < N days since last review)',
      'drill_runbook_trigger_map (PLANNED — every alert source has a runbook)',
      'drill_runbook_links_resolve (PLANNED — every cross-link in runbook resolves)',
    ],
    security: [
      'Runbooks may contain step lists for credential operations — never include the credentials themselves',
      'PR review on runbook changes (no direct push to main)',
      'CODEOWNERS for docs/runbooks/ enforces ownership',
    ],
    scaling: [
      '10x: 10 runbooks comfortably maintained by 5-person team',
      '100x: per-team runbook namespaces; central catalog aggregates',
      'Cost driver: review cadence; quarterly minimum, after-incident always',
    ],
    maturity: {
      mvp: 'Slack threads + tribal knowledge',
      production: '10 runbooks in docs/runbooks/ + cheatsheet index + per-incident updates',
      enterprise: 'Owned per-team + automated freshness drill + trigger-to-runbook map + auto-generated supplements',
    },
    limitations: [
      'No drill yet enforces runbook freshness',
      'No automatic trigger-to-runbook map (operator manually navigates)',
      'No CODEOWNERS for docs/runbooks/ yet',
    ],
    projectFit: [
      'docs/runbooks/DR_RUNBOOK.md, INCIDENT_RESPONSE.md, alertmanager-webhook.md',
      'docs/runbooks/autonomous-loop-cheatsheet.md — loop-mode index',
      'docs/runbooks/genai-rag-failure-scenarios-and-debugging-playbook.md',
      'docs/runbooks/parallel-tool-coordination.md',
    ],
    interviewLine: 'Runbooks live in docs/runbooks/ (versioned, reviewed, greppable). Catalog index is /admin/ops-fabric. Each runbook has owner + trigger + steps + verification + updated-on-incident discipline. The bet: runbooks-in-repo win over wiki because freshness is enforceable.',
    implementationSteps: [
      { step: 'Per-runbook frontmatter', logic: 'owner + trigger + last_review_date.' },
      { step: 'Catalog index', logic: '/admin/ops-fabric lists runbooks with trigger summary.' },
      { step: 'Trigger map', logic: 'Alert source → runbook(s); operator looks up at incident.' },
      { step: 'Verification step', logic: 'Each runbook ends with verify step; documents pass / fail path.' },
      { step: 'Post-incident review', logic: 'Update runbook in same PR as fix; never separate.' },
      { step: 'Quarterly freshness review', logic: 'Drill (planned) flags runbooks > 90 days unreviewed.' },
      { step: 'CODEOWNERS', logic: 'docs/runbooks/ has explicit owner per file or per directory.' },
    ],
    codeExample: {
      language: 'markdown',
      code: `<!-- docs/runbooks/<service>-incident.md — canonical shape -->
---
owner: @praveen
trigger: documind_<svc>_error_rate_5xx > 0.05 for 5min
last_reviewed: 2026-04-30
---

# <Service> incident response

## When to read
You got paged for <svc> error rate > 5%.

## Steps
1. Check breaker state: \`curl /admin/health/breakers\`
2. If breaker open: identify dependency; restart or failover
3. ...

## Verify
Error rate returns below 1% within 5min.

## Recovery if step fails
- Step 2 fail → escalate to <svc>-secondary-oncall
- Step N fail → ADR-019 graceful degradation; degraded banner enabled`,
    },
    starStory: {
      situation: 'Operational knowledge was scattered across Slack + individual heads. New on-call engineers had no canonical reference; even existing runbooks were stale.',
      task: 'Runbooks-in-repo with PR review, owner per file, verifiable steps, post-incident update discipline.',
      action: '10 runbooks in docs/runbooks/; cheatsheet + session logs index the loop pattern; alertmanager-webhook + DR_RUNBOOK + INCIDENT_RESPONSE cover the highest-pager surfaces.',
      result: 'On-call has canonical catalog; runbooks updated as part of incident PRs; freshness drill (planned) catches stale entries.',
    },
    interviewTraps: [
      'Wiki-only docs (drifts; not reviewable)',
      'Auto-generated runbooks (cannot capture WHY)',
      'No post-incident update discipline (every runbook ages out)',
    ],
    finalScript: 'Runbooks-in-repo: versioned, reviewed, greppable, fresh-by-discipline. Per-runbook owner + trigger + steps + verification. Catalog index at /admin/ops-fabric. Post-incident updates in the same PR as the fix. Drill (planned) flags >90-day-unreviewed entries. Wins over wiki because freshness is enforceable.',
  },
  {
    slug: 'integrations',
    title: '2. Integrations (webhooks + MCP servers + RAG sources)',
    status: 'shipped',
    coreConcept: 'External system integrations split into three families: outbound webhooks (alertmanager, council-stats), inbound MCP tool servers (drills, hr, itsm), and RAG ingestion sources (project artifacts, future external feeds). Each family has a contract — webhook payload schema, MCP scope grants, RAG source provenance — and a drill that locks the contract.',
    problem: 'Integrations accrete: a new webhook here, a new MCP tool there, a new RAG source. Without a registry + contract + drill per integration, every new connection is a hidden surprise. When an integration fails (webhook 500, MCP scope drift, RAG source rotted), no operator can name what changed.',
    whyThisApproach: 'Per-family contract: webhooks → URL + retry budget + envelope schema; MCP servers → scope grants + tool catalog + auth; RAG sources → provenance + chunking version + freshness SLA. Per family, a drill locks the contract. New integrations land with their drill in the same commit.',
    whenToUse: ['Outbound notification (Alertmanager → Slack/Discord/PagerDuty)', 'Inbound tool servers (MCP for drills/HR/ITSM)', 'RAG content sources (project artifacts, customer documents)'],
    whenNotToUse: ['Internal service-to-service (use service mesh + correlation_id, not integration registry)', 'One-shot adhoc API calls (no maintenance burden)', 'High-throughput data flows (use Kafka, not webhooks)'],
    input: 'integration spec: family + contract + auth + drill',
    process: [
      'Identify integration family (webhook / MCP / RAG)',
      'Define contract per family (envelope, scope, provenance)',
      'Implement integration with auth + retry + audit',
      'Author drill that exercises the contract',
      'Register in /admin/ops-fabric integrations panel',
      'On failure: drill catches; runbook documents recovery',
    ],
    output: 'Auditable, drill-locked, registered integration.',
    flowchart: `flowchart LR
  ext[External system] -->|webhook IN| api[BFF / API gateway]
  ext -->|MCP tool| mcp[(MCP server)]
  ext -->|RAG source| ing[Ingestion svc]
  api --> drill1[drill_<webhook>]
  mcp --> drill2[drill_<mcp>]
  ing --> drill3[drill_<rag>]
  drill1 -.contract.-> ext
  drill2 -.scope.-> ext
  drill3 -.provenance.-> ext`,
    sequence: `sequenceDiagram
  autonumber
  participant Sys as External system
  participant Reg as Integration registry
  participant D as Drill
  Sys->>Reg: register integration (family + contract)
  Reg->>D: pair with contract drill
  D->>Sys: exercise contract
  D-->>Reg: pass / fail
  alt fail
    Reg-->>Sys: alert + runbook link
  else pass
    Reg-->>Sys: registered
  end`,
    alternatives: [
      { name: 'Ad-hoc integrations', tradeoff: 'No registry; failures invisible; new integration breaks operator trust' },
      { name: 'Single integration framework', tradeoff: 'Forces one shape; webhooks + MCP + RAG have distinct contracts' },
      { name: 'External integration platform (Zapier / n8n)', tradeoff: 'Mature; expensive; gives up source-of-truth control' },
    ],
    challenges: [
      'Per-family contract drift (webhook envelope, MCP scope, RAG provenance evolve independently)',
      'Auth credential rotation (webhook URL, MCP token, RAG source key)',
      'Backpressure when external system slow / unavailable',
      'Audit trail for inbound integrations (what came in, when, who acted)',
    ],
    edgeCases: [
      { case: 'Webhook target down', solution: 'Retry with exponential backoff per global §10.1; circuit breaker after N failures; surfaced in alertmanager' },
      { case: 'MCP tool scope changed', solution: 'Drill catches scope drift; commit must update scope grants in registry' },
      { case: 'RAG source rotted', solution: 'Freshness drill flags; pause re-ingestion; alert source owner' },
    ],
    failureModes: [
      { mode: 'Webhook fires repeatedly to dead URL', detect: 'documind_webhook_5xx_rate spike', recover: 'Circuit breaker opens; pause webhook; operator updates URL via runbook' },
      { mode: 'MCP scope leak', detect: 'Audit row shows tool used outside grant', recover: 'Tighten scope binding; drill catches; refresh tokens' },
      { mode: 'RAG source freshness fail', detect: 'Source SLA breached; drill fires', recover: 'Investigate source; if rotted, deprecate; if delayed, escalate' },
    ],
    monitoring: [
      'documind_integration_request_total{family,outcome}',
      'documind_webhook_retry_total{target}',
      'documind_mcp_tool_invocation_total{tool}',
      'documind_rag_source_freshness_seconds{source}',
    ],
    testing: [
      'drill_alertmanager_receiver_config (locks webhook receiver contract)',
      'drill_council_telemetry (locks council-stats webhook contract)',
      'drill_mcp_<server>_scope (PLANNED — locks MCP scope grants)',
      'drill_rag_source_freshness (PLANNED — locks ingestion SLA)',
    ],
    security: [
      'Webhook URLs are secrets — store in .loop/<service>.env (chmod 600) per global §40 + alertmanager-webhook runbook',
      'MCP scope grants per tool registered + drill-locked',
      'RAG source credentials Vault-rotated quarterly',
      'Audit row per inbound integration call (correlation_id propagated)',
    ],
    scaling: [
      '10x: dozens of integrations across 3 families',
      '100x: per-family registry service (webhook registry, MCP registry, RAG source registry)',
      'Cost driver: outbound webhook cost + RAG ingestion compute',
    ],
    maturity: {
      mvp: 'Hardcoded webhook URLs + ad-hoc MCP servers',
      production: '3-family integrations with contracts + drills + .loop/<service>.env secret pattern',
      enterprise: 'Per-family registries + canary new integrations + automated contract regression suite',
    },
    limitations: [
      'No central integrations dashboard yet',
      'Some MCP scope drills are planned, not shipped',
      'RAG source freshness drill not yet built',
    ],
    projectFit: [
      'infra/observability/alertmanager.yml + docs/runbooks/alertmanager-webhook.md — outbound webhook',
      'mcp/server_drills.py, server_hr.py, server_itsm.py — inbound MCP servers',
      'services/ingestion-svc/ — RAG sources',
      '.loop/<service>.env (chmod 600) — webhook secret pattern',
    ],
    interviewLine: 'Integrations split into three families — outbound webhooks, inbound MCP tools, RAG ingestion sources. Each family has its own contract; each integration ships with a drill that locks that contract. .loop/<service>.env (chmod 600) is the webhook-secret pattern; Vault rotates credentials quarterly.',
    implementationSteps: [
      { step: 'Per-family contract', logic: 'Webhook envelope, MCP scope grants, RAG provenance — different shapes per family.' },
      { step: 'Integration registry', logic: 'Inventory of every integration with contract reference + drill reference.' },
      { step: 'Drill per integration', logic: 'New integration ships with drill in same commit; locks the contract.' },
      { step: 'Secret discipline', logic: '.loop/<service>.env (chmod 600) for webhook URLs + tokens; Vault rotation.' },
      { step: 'Audit row per call', logic: 'correlation_id propagated; inbound + outbound calls audited.' },
      { step: 'Recovery runbook', logic: 'Per-integration failure mode → recovery runbook in docs/runbooks/.' },
      { step: 'Drift detection', logic: 'Drill fires on contract drift; PR review surfaces immediately.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# Future: docs/architecture/integrations.yaml — registry shape
integrations:
  outbound_webhooks:
    - name: alertmanager-shared
      target_env_var: ALERTMANAGER_WEBHOOK_URL
      contract: webhook-v1 (alertmanager-native JSON)
      runbook: docs/runbooks/alertmanager-webhook.md
      drill: mcp/tests/drill_alertmanager_receiver_config.py
      retry_budget: 3 with exponential backoff

    - name: council-stats
      target_env_var: COUNCIL_STATS_WEBHOOK
      contract: generic-json-v1
      runbook: docs/runbooks/council-telemetry.md
      drill: mcp/tests/drill_council_telemetry_runner.py

  inbound_mcp:
    - name: drills
      server: mcp/server_drills.py
      tools: [drill.list, drill.run]
      scopes: [drill:read, drill:run]

    - name: hr
      server: mcp/server_hr.py
      tools: [hr.search_employees, hr.get_employee]
      scopes: [hr:read]

  rag_sources:
    - name: project-adrs
      source: docs/architecture/adr/*.md
      chunking: §43-aligned
      freshness_sla: 5min`,
    },
    starStory: {
      situation: 'Integrations were ad-hoc: webhook URLs in .env, MCP servers without scope-grant audit, RAG sources without freshness SLA. New integrations were silent additions.',
      task: 'Three-family integration registry + contract + drill + .loop/<service>.env secret pattern.',
      action: '.loop/alertmanager.env + .loop/council-stats.env land webhook secrets at chmod 600. drill_alertmanager_receiver_config locks the webhook receiver contract. MCP servers (drills/hr/itsm) ship with explicit scope grants. RAG sources documented with freshness SLA.',
      result: 'Integrations are visible, drill-locked, runbook-recoverable. Contract drift fires the drill in PR review. .loop/<service>.env secret pattern reused across council-stats + alertmanager + future integrations.',
    },
    interviewTraps: [
      'Hardcoded webhook URLs in repo (secret leak)',
      'MCP without scope grants (excessive agency per §38)',
      'RAG source without freshness SLA (stale data masquerades as fresh)',
    ],
    finalScript: 'Three integration families — outbound webhooks, inbound MCP tools, RAG sources — each with a per-family contract + drill + recovery runbook. .loop/<service>.env (chmod 600) is the webhook-secret pattern. Drift catches at PR review via the drill; failure recovery via the runbook. Without this discipline, integrations are silent surprises.',
  },
  {
    slug: 'debugging-fixing',
    title: '3. Debugging + fixing (correlation_id-led incident triage)',
    status: 'shipped',
    coreConcept: 'Incident triage built on correlation_id propagation: every request tagged at gateway → propagated through BFF → backends → audit row. When something breaks, the operator pulls the correlation_id from the user-facing error envelope and reconstructs the full trace: spans, logs, audit row, and any draft / advice / decision rows. Fixing flow: reproduce → bisect → fix → drill the fix.',
    problem: 'Incident triage without trace cohesion is detective work. Logs scattered across services, audit rows in another DB, advice JSON in a third. Even with all three open, the operator has to manually correlate by approximate timestamp. Correlation_id-led triage turns the detective work into a single query.',
    whyThisApproach: 'correlation_id is server-generated at gateway, never accepted from client, propagated via OTel baggage + headers to every downstream service. Every span, every log line, every audit row carries it. The user-facing error envelope returns it so the operator can paste-search across all systems with one string. Per global §47 + §48, this is the explainability + observability foundation.',
    whenToUse: ['User-reported error (paste correlation_id, find trace)', 'Backend exception (cross-reference logs to advice/audit)', 'Council advice that looks wrong (find chain via correlation_id)', 'Performance regression (find slow spans by correlation_id pattern)'],
    whenNotToUse: ['Pre-traffic failures (correlation_id not yet generated)', 'Static-asset 404s (no correlation_id needed)', 'Dev-loop fast iteration (printf debugging is faster for tight loops)'],
    input: 'correlation_id from error envelope OR user report',
    process: [
      'User hits error; UI shows {detail, error_code, correlation_id}',
      'Operator pastes correlation_id into trace UI (Jaeger / OTel)',
      'Trace shows span tree across services',
      'Each span links to log lines (correlation_id field)',
      'For LLM events: correlation_id → audit row in events table → advice chain',
      'Bisect: at which span did the error originate?',
      'Fix: in the originating service; drill the fix to lock regression',
    ],
    output: 'Reproduced incident + root cause + fix + drill regression.',
    flowchart: `flowchart LR
  err[User error] --> env[Error envelope w/ correlation_id]
  env --> trace[Trace UI]
  trace --> spans[Span tree]
  spans --> logs[Logs by correlation_id]
  spans --> audit[Audit row by correlation_id]
  spans --> advice[Advice chain]
  logs --> bisect[Bisect to origin]
  audit --> bisect
  advice --> bisect
  bisect --> fix[Fix in origin service]
  fix --> drill[Drill the fix]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Op as On-call
  participant T as Trace UI
  participant L as Logs
  participant A as Audit
  U->>Op: error envelope with correlation_id
  Op->>T: query by correlation_id
  T-->>Op: span tree
  Op->>L: grep correlation_id
  Op->>A: SELECT WHERE correlation_id=?
  L-->>Op: log lines
  A-->>Op: audit + advice rows
  Op->>Op: identify origin span
  Op->>Op: write fix
  Op->>Op: write drill that exercises fix`,
    alternatives: [
      { name: 'No correlation_id', tradeoff: 'Detective work; multiply triage time; impossible at scale' },
      { name: 'Per-service trace IDs', tradeoff: 'Each service has its own; cross-service correlation lost' },
      { name: 'Distributed tracing (OTel) without correlation_id', tradeoff: 'Trace ID exists; binding to logs + audit weaker' },
    ],
    challenges: [
      'correlation_id propagation across every service hop',
      'Server-generation discipline (never accept client-supplied)',
      'OTel baggage vs custom header (use both for compatibility)',
      'Audit row indexing on correlation_id (cardinality cost)',
    ],
    edgeCases: [
      { case: 'Async retry hop loses correlation_id', solution: 'Retry helper preserves header; drill drill_baggage_propagation locks' },
      { case: 'Background job spawned mid-request', solution: 'Job inherits correlation_id; new sub-correlation_id linked' },
      { case: 'User reports issue without error envelope', solution: 'Reproduce in dev with intentional correlation_id; trace forward' },
    ],
    failureModes: [
      { mode: 'correlation_id missing on log line', detect: 'grep returns nothing for known incident', recover: 'Audit logger middleware; CI step asserts every log has the field' },
      { mode: 'correlation_id rewritten by middleware', detect: 'Two correlation_ids in one trace', recover: 'Audit middleware order; first-write-wins discipline' },
      { mode: 'Audit row missing correlation_id index', detect: 'Slow audit queries by correlation_id', recover: 'CREATE INDEX; backfill if needed' },
    ],
    monitoring: [
      'documind_incidents_total{root_cause}',
      'documind_mttr_seconds_p95 (mean time to resolve)',
      'documind_correlation_id_propagation_failures_total',
      '/admin/forensics correlation_id query UI',
    ],
    testing: [
      'drill_baggage_propagation (locks correlation_id propagation across hops)',
      'drill_correlation_id_in_audit (every audit row has correlation_id)',
      'drill_correlation_id_in_log (every log line has correlation_id)',
      'drill_<bug>_regression (per-fix drill that locks the specific bug)',
    ],
    security: [
      'correlation_id is server-generated; never accept client-supplied (forgery prevention)',
      'correlation_id appears in user-facing error envelope (deliberate; non-sensitive)',
      'PII NOT in correlation_id; opaque UUID v4',
      'Audit row immutable; correlation_id is the join key',
    ],
    scaling: [
      '10x: in-process correlation_id propagation; sub-µs',
      '100x: distributed tracing (OTel + Jaeger / Tempo); per-tenant trace storage',
      'Cost driver: trace storage; sample at 1% under high load; force-sample on error',
    ],
    maturity: {
      mvp: 'No correlation_id; logs scattered',
      production: 'Server-generated correlation_id propagated across BFF + backend + audit; OTel baggage; /admin/forensics UI',
      enterprise: 'Full distributed tracing + per-tenant trace isolation + automated bisection + LLM-assisted root-cause (per /admin/aiops/deep)',
    },
    limitations: [
      'Per-fix drill discipline is operator-enforced (not yet automated)',
      'No LLM-assisted bisection (per /admin/aiops/deep#llm-incident-summarization, planned)',
      'Trace storage limited to in-memory (Jaeger out-of-process, not deployed in compose)',
    ],
    projectFit: [
      'libs/py/documind_core/observability.py — correlation_id middleware',
      'services/frontend/lib/sidecar.ts — BFF correlation_id helper',
      '/admin/forensics — operator triage UI',
      '/admin/tracing/deep — OTel baggage propagation deep-dive',
      'docs/runbooks/genai-rag-failure-scenarios-and-debugging-playbook.md',
    ],
    interviewLine: 'Debugging is correlation_id-led: server-generated at gateway, propagated via OTel baggage, present in every log line + audit row + advice chain. User error envelope returns it so the operator can paste-search across all systems with one string. Per-fix drill locks the bug from regression.',
    implementationSteps: [
      { step: 'Server-generate correlation_id', logic: 'BFF / gateway middleware UUID v4 per request; never accept client-supplied.' },
      { step: 'OTel baggage', logic: 'baggage.set(correlation_id); auto-propagated to downstream services.' },
      { step: 'Custom header for compatibility', logic: 'X-Correlation-Id alongside baggage; defensive against non-OTel callers.' },
      { step: 'Logger middleware', logic: 'Every log line includes correlation_id field; CI asserts coverage.' },
      { step: 'Audit row index', logic: 'CREATE INDEX on correlation_id; sub-ms lookup.' },
      { step: 'Error envelope returns id', logic: '{detail, error_code, correlation_id}; user pastes in support.' },
      { step: 'Per-fix drill', logic: 'Every bug-fix ships drill_<bug>_regression that fails before fix, passes after.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/observability.py — correlation_id middleware
import uuid
from contextvars import ContextVar
from fastapi import Request

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

async def correlation_id_middleware(request: Request, call_next):
    # Server-generated; never trust client-supplied for security
    cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = cid
    return response

def get_correlation_id() -> str:
    return correlation_id_var.get()

# Logger filter — every log line carries it
class CorrelationIdFilter:
    def filter(self, record):
        record.correlation_id = get_correlation_id()
        return True`,
    },
    starStory: {
      situation: 'Incident triage was 30+ minutes per incident: logs scattered, advice in DB, audit in another. Operators reconciled by approximate timestamp; data fragmented during peak load.',
      task: 'correlation_id propagated everywhere: server-generated, OTel baggage, audit row, log line, error envelope.',
      action: 'observability.py middleware. OTel baggage propagation. Custom X-Correlation-Id header. Logger filter. Audit row index. Error envelope returns the id. /admin/forensics UI lets operator paste + reconstruct trace.',
      result: 'Triage time dropped from 30+ minutes to under 5. Per-fix drills lock specific bugs from regression. /admin/forensics is the operator entry point. Per /admin/aiops/deep#llm-incident-summarization, the LLM-assisted bisection is the next step.',
    },
    interviewTraps: [
      'Client-supplied correlation_id (forgery; use server-generated)',
      'Logs without correlation_id field (grep returns nothing)',
      'Audit row missing index on correlation_id (slow lookup)',
    ],
    finalScript: 'Debugging is correlation_id-led incident triage: server-generated at gateway, OTel-baggaged through every hop, indexed in audit + log. /admin/forensics is the entry. Per-fix drill locks each bug from regression. The bet: every triage starts with one paste-able string. Without it, triage is detective work; with it, triage is a single query.',
  },
];

export default function OpsFabricDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Ops fabric deep dive</h1>
          <p className="page-subtitle">
            Three operational substrates — runbooks (incident + lifecycle
            catalog), integrations (webhooks + MCP + RAG sources), and
            debugging (correlation_id-led triage) — explained through the
            universal 20-dimension framework.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/forensics', label: 'Forensics (trace → draft → audit → HITL)', why: 'forensics UI is where correlation_id-led triage actually happens; this page details the substrate' },
          { href: '/admin/tracing/deep', label: 'Tracing + OTel baggage', why: 'correlation_id propagates via OTel baggage; tracing deep-dive details that mechanism' },
          { href: '/admin/aiops/deep', label: 'AIOps deep-dive', why: 'planned LLM incident summarization composes with correlation_id-led triage; this page sets the foundation' },
          { href: '/admin/agent-registry/deep', label: 'Agent registry', why: 'integrations include MCP tool servers; agent registry covers role-side; this page covers integration-side' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'no runbook + no audit row = release blocked per §38 hard-stop' },
        ]}
      />
    </>
  );
}
