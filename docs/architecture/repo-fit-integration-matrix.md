# Repo-Fit Integration Matrix

This document maps common external integrations against the current repo shape.

Status meanings:

- `Strong fit`: aligns directly with current architecture
- `Partial fit`: feasible with moderate new work
- `Future fit`: conceptually aligned but requires substantial new capability

## 1. Summary matrix

| Integration | Primary use | Repo fit | Why |
|---|---|---|---|
| Slack | internal assistant, approvals, alerts | Strong fit | fits gateway + inference + MCP + audit + replay patterns well |
| SharePoint | enterprise knowledge sync | Strong fit | fits ingestion, retrieval, tenant-aware governance, provenance |
| Google Drive | document sync and retrieval | Strong fit | same ingestion and retrieval fit as SharePoint |
| SQL DB | operational reads, analytics, Text2SQL | Partial fit | core SQL use fits; safe Text2SQL needs new guardrails and execution controls |
| Facebook / Meta | leads, campaign sync, analytics | Partial fit | fits workflow and analytics direction, but needs dedicated connector/service logic |
| WhatsApp | customer messaging and action shell | Partial fit | fits agent + workflow model, but needs channel adapter, identity mapping, and policy layer |

## 2. Why each connector fits

### Slack
- maps well to internal users
- supports assistant, approval, and alert flows
- easy fit with governance and replay-heavy workflows

### SharePoint
- natural enterprise knowledge source
- strong fit with ingestion, chunking, embedding, retrieval
- good fit with tenant-aware permissions if implemented carefully

### Google Drive
- same core fit as SharePoint
- simpler starting point for file sync and source provenance

### SQL DB
- current repo already uses SQL heavily for core services
- direct SQL integrations fit well
- Text2SQL is only partial because safe query generation and review logic are not yet first-class

### Facebook / Meta
- fits future growth, ads, and lead scenarios
- requires connector auth, webhook handling, and campaign data normalization

### WhatsApp
- good fit as a communication surface
- less mature fit than Slack because external-customer identity, consent, and messaging constraints are more complex

## 3. Service-layer mapping

| Integration | Best owning layer in this repo |
|---|---|
| Slack | gateway + inference + MCP-backed action flows |
| SharePoint | ingestion-svc + retrieval-svc + governance constraints |
| Google Drive | ingestion-svc + retrieval-svc + governance constraints |
| SQL DB | service-owned stores; optional safe query service for Text2SQL |
| Facebook / Meta | future connector or campaign service + analytics ingestion |
| WhatsApp | future connector adapter + gateway + inference/action flows |

## 4. Governance complexity by integration

| Integration | Main governance risk |
|---|---|
| Slack | internal identity mapping and approval misuse |
| SharePoint | permission mapping and confidential library leakage |
| Google Drive | ACL drift and shared-drive scoping mistakes |
| SQL DB | tenant filter bypass, PII exposure, unsafe write/query execution |
| Facebook / Meta | ad-account routing, spend data isolation, secret handling |
| WhatsApp | PII, consent, identity ambiguity, external-user action safety |

## 5. Best implementation order

1. Slack
2. SharePoint
3. Google Drive
4. SQL read-only analytics integration
5. Facebook / Meta
6. WhatsApp

## 6. Bottom line

The strongest near-term integrations for this repo are knowledge and internal workflow connectors:

- Slack
- SharePoint
- Google Drive

SQL fits strongly at the service level and only partially for Text2SQL. Facebook and WhatsApp fit the broader platform direction, but they require more connector-specific product and governance work.
