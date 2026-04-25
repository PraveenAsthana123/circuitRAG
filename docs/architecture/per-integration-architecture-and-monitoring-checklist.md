# Per-Integration Architecture and Monitoring Checklist

This document gives a practical checklist for designing and operating each major connector family.

Use the same audit frame for every integration:

- purpose
- entry path
- auth
- data flow
- failure handling
- monitoring
- tracking
- operations

## 1. Checklist template

For every connector, answer:

### Architecture
- What business workflow does this connector enable?
- Is it inbound, outbound, sync, or bidirectional?
- Which service owns the connector?
- Does it enter through webhook, polling, scheduled sync, or user-triggered call?
- Where does identity or tenant context come from?
- What data is stored locally and what remains external?

### Security and governance
- How is auth handled?
- How are secrets rotated?
- What scopes or permissions are required?
- How are tenant boundaries enforced?
- Is PII present?
- What must be audited?

### Reliability
- Is the integration idempotent?
- What happens on duplicate delivery?
- What happens on timeout or rate limit?
- Is degraded mode allowed?
- Is replay supported?

### Monitoring
- What are the success/failure metrics?
- What latency matters?
- What backlog or sync lag matters?
- What denials or policy events matter?

### Tracking
- What correlation ID is carried?
- What external object IDs are stored?
- What actor identity is stored?
- What audit events are required?

## 2. WhatsApp checklist

### Architecture
- define inbound webhook handler ownership
- define outbound messaging service ownership
- map conversation to tenant/account/workspace
- map external phone identity to internal user/contact model

### Monitoring
- inbound webhook success rate
- outbound delivery success rate
- duplicate inbound dedupe count
- template rejection count
- downstream action success/degraded rate

### Tracking
- external message ID
- conversation ID
- phone/account/workspace mapping
- correlation ID into backend actions
- audit event for high-risk actions

## 3. SQL DB checklist

### Architecture
- service owns its own SQL access pattern
- define read-only vs read-write credentials
- define query ownership by service
- separate Text2SQL execution path from ordinary application SQL

### Monitoring
- query latency by class
- pool saturation
- deadlocks and lock waits
- rollback rate
- slow-query count
- tenant-denial or policy-block count for Text2SQL

### Tracking
- request correlation ID
- query class or template ID
- external user or actor ID
- table/domain scope touched
- audit event for privileged query execution

## 4. SharePoint checklist

### Architecture
- define scheduled sync ownership
- define delta-token or cursor handling
- preserve document provenance and source link
- preserve permission model mapping
- define delete/tombstone handling

### Monitoring
- sync success/failure
- files scanned/indexed/skipped
- permission mapping failures
- parse failures by type
- delta lag
- duplicate detection

### Tracking
- site ID
- drive/library ID
- document ID/version
- source permissions snapshot
- sync run ID and correlation

## 5. Slack checklist

### Architecture
- define slash-command or event-webhook entrypoint
- define approval and alert workflows
- map Slack user to enterprise identity
- ensure Slack is not a policy bypass around governed backend actions

### Monitoring
- slash-command success rate
- event delivery retries
- approval completion rate
- action denial count
- degraded action count
- webhook verification failures

### Tracking
- Slack team/workspace ID
- channel ID
- user ID
- thread ID
- correlation ID through backend actions

## 6. Facebook / Meta checklist

### Architecture
- define campaign sync ownership
- define lead webhook ownership
- normalize ad account, campaign, creative, and lead IDs
- separate analytics ingestion from actioning workflows

### Monitoring
- sync success rate
- lead webhook volume
- API error class distribution
- rate-limit count
- token expiry or auth failure count
- attribution mismatch or mapping failures

### Tracking
- ad account ID
- campaign ID
- creative ID
- lead ID
- tenant/account mapping
- correlation ID into downstream workflows

## 7. Google Drive checklist

### Architecture
- define scheduled sync ownership
- map shared folders or drives to tenant knowledge scopes
- preserve source link and file version
- handle Google Docs export path explicitly
- define deletion and stale-index cleanup behavior

### Monitoring
- sync run success/failure
- files scanned/indexed/skipped
- export failures
- ACL mapping failures
- rate-limit and quota errors
- stale index lag

### Tracking
- file ID
- drive/shared-drive ID
- owner/workspace identity
- file version or modified timestamp
- sync run ID and correlation

## 8. Cross-integration monitoring matrix

| Integration | Success metrics | Failure metrics | Lag/backlog metrics | Governance metrics |
|---|---|---|---|---|
| WhatsApp | inbound/outbound success | webhook failure, template rejection | retry backlog | PII masking, blocked action count |
| SQL DB | query success | timeout, deadlock, rollback | pool saturation | denied query count, audit count |
| SharePoint | sync success, files indexed | auth fail, parse fail | delta lag | permission mapping failure |
| Slack | command success, approval completion | webhook fail, token fail | event retry backlog | denial count, actor mapping failure |
| Facebook | sync success, lead ingestion | auth fail, rate limit | webhook backlog | account mapping failure |
| Google Drive | sync success, files indexed | auth fail, export fail | sync lag | ACL mapping failure |

## 9. Operational checklist before production

- connector secrets stored in managed secret store
- least-privilege scopes configured
- tenant mapping tested
- duplicate delivery path tested
- replay or re-sync path tested
- dashboards exist for success/failure/lag
- correlation IDs preserved end to end
- audit events defined for sensitive actions
- runbook exists for token expiry, rate limits, and webhook failure

## 10. Bottom line

Every connector should be treated like a mini-product surface:

- owned by one service
- monitored explicitly
- audited where needed
- replayable or recoverable
- isolated by tenant and scope

That is what separates a demo connector from a production integration.
