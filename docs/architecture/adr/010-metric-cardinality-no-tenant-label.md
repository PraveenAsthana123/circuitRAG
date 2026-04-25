# ADR-010: No `tenant_id` label on Prometheus series — cardinality discipline

## Status

Accepted — applied across commits `19ff1eb` (worker outcomes),
`334917e` (backlog age), `aa255a0` (token cost), and earlier
breaker / audit metrics.

## Context

Tenant-scoped systems are tempting to label by tenant_id. Per-tenant
dashboards are useful; per-tenant alerts are useful. But Prometheus
labels are dimensional — every distinct labelset materializes a
separate time series, and series count is the load-bearing cost
driver of a metrics backend.

A 1000-tenant deployment with a single tenant-labelled counter is
1000 series. Combined with `outcome` (5 values) and `namespace`
(3 values) it's 15,000 series. One careless `tenant_id` label on
a metric used elsewhere can blow Prometheus over.

## Decision

**No metric in this repo carries a `tenant_id` label.** The decision
applies to:

* `documind_circuit_breaker_*` (state, transitions, opens, rejections)
* `documind_audit_write_failures_total{action, error_type}`
* `documind_mcp_tool_calls_total{namespace, tool, outcome}`
* `documind_draft_replay_total{namespace, outcome}`
* `documind_draft_pending_age_seconds{namespace}`
* `documind_inference_tokens_total{model, kind}`

Labels chosen are bounded sets:

* `namespace` — one per MCP server (hr, itsm, drills, ...)
* `outcome` — closed enum (replayed, failed, cb_wait, etc.)
* `action` — finite list of audit action names
* `model` — finite list of configured models
* `kind` — `prompt | completion`
* `error_type` — exception class name (bounded by Python's class
  registry; in practice ~10 distinct values across the audit path)

Per-tenant cost / health rollups are computed offline from
structured logs (Loki) which already carry `tenant_id` per line.

## Consequences

* Metrics back-end cost stays linear in number of services + number
  of dependencies, not in number of tenants.
* Future tenant-scoped operations either go to logs (cheap to
  filter, expensive to query) or quantize tenant into buckets
  (e.g. tenant_size: small / medium / large). Both are explicit
  decisions that future ADRs can reference.
* Drills that need per-tenant assertion isolation use UUID-tenants
  (`drill_worker_metrics`, `drill_worker_auto_reject`,
  `drill_retrieval_tenant_isolation`) — same data is in the metric
  values, just not in labels.
* The discipline is enforced by drill code review; if a future
  metric definition adds `tenant_id` to labelnames, this ADR is
  the document that says "no, here's why."
