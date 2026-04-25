# Connector Integration Scenarios

This document groups common enterprise connector scenarios relevant to this repo and adjacent AI platform use cases.

Primary connector families covered here:

- WhatsApp
- SQL databases
- SharePoint
- Slack
- Facebook / Meta
- Google Drive

## 1. WhatsApp scenarios

WhatsApp belongs to the customer communication and conversational workflow layer.

### Core scenarios
- user sends question through WhatsApp and receives grounded answer
- user sends action request through WhatsApp and backend routes it through governed APIs
- WhatsApp conversation starts a lead capture or support workflow
- inbound message contains attachment that must be ingested safely
- outbound notification is sent after backend workflow completes

### Failure scenarios
- webhook delivery fails
- duplicate inbound message arrives
- media attachment URL expires before processing
- third-party API rate limit is hit
- phone number or template policy error blocks outbound response

### Governance scenarios
- PII in messages is masked in logs
- unsupported action request is denied cleanly
- actor identity is tracked as channel-originated user
- tenant or account routing selects the correct backend workspace

### Monitoring signals
- inbound webhook success rate
- outbound delivery success rate
- duplicate message count
- webhook latency
- template rejection count
- downstream action success/degraded rate

## 2. SQL database scenarios

SQL integration belongs to analytics, operational data access, and Text2SQL-style query workflows.

### Core scenarios
- service reads operational data from SQL database
- service writes controlled workflow state to SQL database
- reporting flow queries aggregate metrics
- Text2SQL generates safe read-only query
- cross-service SQL access respects ownership boundaries

### Failure scenarios
- connection pool exhaustion
- slow query causes request timeout
- deadlock or transaction conflict
- schema drift breaks query path
- read replica lag creates stale analytics view

### Governance scenarios
- tenant filtering is enforced
- PII fields are masked or excluded
- write access is restricted to owned services
- read-only integration account cannot mutate schema or data

### Monitoring signals
- query latency
- error rate by query class
- connection saturation
- deadlock count
- transaction rollback count
- expensive query count

## 3. SharePoint scenarios

SharePoint belongs to enterprise document ingestion and knowledge synchronization.

### Core scenarios
- scheduled sync imports documents from SharePoint
- metadata and permissions are preserved
- changed documents are re-indexed
- deleted documents are removed or tombstoned in search index
- enterprise policies and knowledge articles are retrieved for RAG

### Failure scenarios
- OAuth token expires
- sync job misses delta window
- large file cannot be parsed
- permission mismatch exposes wrong document set
- duplicate sync creates duplicate documents

### Governance scenarios
- SharePoint permissions map to tenant or user scope
- confidential libraries are excluded from general retrieval
- document provenance is stored
- access-denied documents never become retrievable in the wrong context

### Monitoring signals
- sync job success/failure
- files discovered vs files indexed
- delta sync lag
- permission mapping failures
- parse failures by file type
- duplicate document detection count

## 4. Slack scenarios

Slack belongs to the internal assistant, approval, alerting, and operator workflow layer.

### Core scenarios
- user asks internal assistant question from Slack
- Slack action button triggers governed backend action
- Slack notification reports degraded mode, backlog, or replay completion
- approval request is sent to Slack and response is captured
- Slack thread preserves context for follow-up action

### Failure scenarios
- slash command verification fails
- Slack event delivery is retried and dedupe is needed
- bot token expires or is revoked
- response timeout occurs before backend finishes
- chat UX hides backend degraded state

### Governance scenarios
- channel-based access restrictions apply
- user identity maps to enterprise identity correctly
- actions requiring approval are not auto-executed
- audit includes Slack user, channel, and correlation context

### Monitoring signals
- slash command success rate
- event webhook latency
- approval completion rate
- duplicate event count
- action denial count
- replay/degraded outcome counts from Slack-originated requests

## 5. Facebook / Meta scenarios

Facebook belongs to ads, lead generation, campaign analytics, and growth workflows.

### Core scenarios
- campaign metrics are imported from Meta Ads
- lead form submission triggers backend workflow
- creative generation output is published to campaign review flow
- ad performance data feeds optimization or reporting
- audience or campaign sync updates internal state

### Failure scenarios
- API token expires
- ad account permission is missing
- webhook lead delivery fails
- campaign API rate limit is hit
- field mapping changes break ingestion

### Governance scenarios
- ad account routing matches tenant
- spend, CPA, ROAS, and attribution data are isolated correctly
- campaign actions require appropriate role
- API credentials are stored and rotated securely

### Monitoring signals
- campaign sync success rate
- lead ingestion count
- webhook retry count
- API error class distribution
- rate-limit count
- attribution mismatch count

## 6. Google Drive scenarios

Google Drive belongs to document ingestion, collaboration knowledge sync, and file-based retrieval.

### Core scenarios
- scheduled Drive sync ingests new files
- shared folder maps to tenant knowledge source
- Google Docs content is exported and indexed
- changes trigger re-indexing
- deleted files are removed from active index

### Failure scenarios
- OAuth scope is insufficient
- file export format unsupported
- shared-drive permissions change after indexing
- duplicate sync creates redundant records
- rate limit or quota error blocks sync

### Governance scenarios
- Drive file ACLs map to retrieval scope
- confidential files stay excluded from general answers
- provenance and source link are retained
- file owner and workspace identity are tracked

### Monitoring signals
- sync run success/failure
- files scanned/indexed/skipped
- export failure count
- ACL mapping errors
- stale index lag
- duplicate file detection count

## 7. Cross-connector scenarios

These matter when multiple connectors exist in the same platform:

- one tenant uses Slack and SharePoint while another uses WhatsApp and Drive
- same user asks question in Slack and answer is grounded from SharePoint and Drive
- Facebook lead arrives and creates workflow that notifies Slack or WhatsApp
- Text2SQL and document retrieval combine in one answer path
- connector token rotation happens without downtime
- one connector is degraded while others remain healthy
- connector replay recovers missed inbound events after outage

## 8. Highest-value starter scenarios

1. Slack internal assistant flow
2. SharePoint knowledge sync with permission preservation
3. Google Drive sync with provenance and ACL mapping
4. Facebook lead webhook ingestion
5. WhatsApp inbound/outbound conversational workflow
6. SQL read-only analytics and safe query execution
