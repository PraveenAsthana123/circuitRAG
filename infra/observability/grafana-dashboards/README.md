# Grafana dashboards

## `documind-overview.json`

This dashboard is now auto-provisioned by local Grafana via:

- `infra/observability/grafana-dashboards.yaml`
- `docker-compose.yml` Grafana volume mounts

So if the local observability stack is up, the dashboard should appear
under the `DocuMind` folder without a manual import step.

Panels now cover two sources:

- app/runtime metrics that `libs/py/documind_core/` and services emit
  - circuit breaker state + failures
  - retrieval quality
  - CCB interrupts/warnings
  - token breaker rejects
  - agent stops
  - ingest chunk decisions
  - observability breaker skips
- infra metrics from the local exporters
  - `node-exporter` host CPU / memory / filesystem
  - `cadvisor` container CPU / memory

If an app panel is empty, the corresponding code path probably has not executed yet. If an infra panel is empty, the likely issue is that `node-exporter` / `cadvisor` are not running or Prometheus is not scraping them.

## Previously shipped `slo-burn.json` — REMOVED

The earlier SLO burn-rate dashboard referenced `http_requests_total`, `http_request_duration_seconds_bucket`, and `documind_eval_faithfulness` — none of which any service in this repo emits today. It was cargo-culted from a real SLO dashboard without verifying the metric producers existed.

It will come back once:

1. OpenTelemetry FastAPI auto-instrumentation is actually running in prod (the code path exists; the stack has never been started), producing `http_server_request_duration_seconds` (OTel) or `http_requests_total` (Prom exporter).
2. evaluation-svc writes `documind_eval_*` gauges after each run.

Until then, shipping a dashboard for those metrics would be misleading.
