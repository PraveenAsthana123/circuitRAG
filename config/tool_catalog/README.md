# Tool catalog — 9-axis operational spec

Per CLAUDE.md §44 (iter-74), §47 (architecture is observable), §47.6
(DevSecOps shift-left), §50.5.3 (read-only operator surface), §51
(forensic substrate).

## Why this exists

The user asked, in the autonomous-loop session: *"each tool must have
fallback plan, input/process/output plan, integration plan, testing
plan, monitoring plan, visualization plan on UI, integration with
OpenTelemetry / Kibana / any visualization, OPA/Rego, observability,
log/trace/track."*

The naive answer is per-server prose docs. That doesn't compose:
docs drift, are unsearchable, and can't be drilled. This catalog is
**data not docs** — one YAML per tool namespace, loaded by the fleet
health monitor, surfaced in the UI as drill-down panels, drilled for
schema conformance.

## The 9 axes

Every catalog entry MUST populate ALL 9 axes for the tool to count as
"production-grade". Drilled at `mcp/tests/drill_tool_catalog_schema.py`.

| Axis | Field | What it answers |
|---|---|---|
| 1 | `fallback` | What does the system do when this tool is unreachable / failing? |
| 2 | `io` | Input shape, Process steps, Output shape (for each tool in namespace) |
| 3 | `integration` | Upstream/downstream tools + the contracts |
| 4 | `testing` | Drill path + smoke-test command + cadence |
| 5 | `monitoring` | Metrics emitted (Prometheus names) + alert thresholds |
| 6 | `visualization` | UI page that surfaces this tool's state |
| 7 | `policy` | OPA/Rego bundle + decision-rule list (default-deny) |
| 8 | `observability` | OTel span name + Jaeger query + Kibana log query |
| 9 | `runbook` | Path to ops/runbook/<ns>.md (rolling — created per-tool) |

## Schema

```yaml
namespace: <ns>            # MUST match mcp/server_<ns>.py
status_target: WORKING     # WORKING | DEGRADED-OK | OPTIONAL
owner: <team-or-role>      # for on-call rotation

fallback:
  on_unreachable: <action>     # short string e.g. "skip; log degraded"
  on_failing: <action>         # e.g. "circuit-break for 60s; alert oncall"
  on_not_installed: <action>   # e.g. "feature flag off; UI hides namespace"

io:
  - tool: <ns>.<name>
    input_schema_ref: <jsonschema-or-pydantic-class>
    process: |
      Numbered steps describing what the tool does internally.
    output_schema_ref: <jsonschema-or-pydantic-class>
    side_effects: read|write
    avg_latency_ms: <int>
    p95_latency_ms: <int>
    cost_per_call_usd: <float>     # 0 for self-hosted

integration:
  upstream: [<ns>...]            # who calls this tool
  downstream: [<ns>...]          # who this tool calls
  contracts:
    - { producer: <ns>, consumer: <ns>, schema: <ref> }

testing:
  drill: mcp/tests/drill_mcp_<ns>_server.py
  smoke_cmd: <one-shot CLI smoke test>
  cadence: <iter|hourly|daily>
  scheduled_via: <cron-line-or-makefile-target>

monitoring:
  metrics:
    - { name: <prom_name>, type: counter|histogram|gauge, alert_at: "<expr>" }
  alerts:
    - { name: <alert_name>, severity: P1|P2|P3, route: <oncall-channel> }

visualization:
  ui_page: /admin/<path>
  embed_in: [/admin/dashboard, /admin/mcp-fleet-health]
  panels: [status, latency_p95, error_rate, qps]

policy:
  opa_bundle: config/policies/<ns>.rego        # may be shared; ok to point at agent_dispatch.rego
  rules: [<rule_id>...]
  default: deny

observability:
  otel:
    span_name: mcp.<ns>.<tool>
    attrs: [tenant_id, request_id, scopes_granted]
  jaeger:
    query_template: "service=mcp-<ns>&operation=mcp.<ns>.<tool>"
  kibana:
    index: filebeat-mcp-*
    query_template: "kubernetes.labels.app:mcp-<ns> AND request_id:{request_id}"
  log_fields: [request_id, tenant_id, actor, tool, latency_ms, outcome]

runbook: ops/runbook/<ns>.md
```

## Catalog files

One YAML per namespace under this directory. Drill enforces:

- File name == `<namespace>.yaml`
- All 9 axes present
- `namespace` field matches filename
- Every `io[].tool` starts with `<namespace>.`
- Every metric name has alert_at OR is documented as "informational"

## Adoption discipline

Adding a new MCP server MUST ship:

1. `mcp/server_<ns>.py` (existing pattern)
2. `config/tool_catalog/<ns>.yaml` (this catalog entry)
3. `mcp/tests/drill_mcp_<ns>_server.py` (existing pattern)
4. `ops/runbook/<ns>.md` (rolling — can be a stub on first ship)

The catalog drill (`drill_tool_catalog_schema.py`) blocks merges if
any of (1) lacks (2).
