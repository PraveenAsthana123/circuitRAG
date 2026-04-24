# Grafana dashboards

## `documind-overview.json`

Panels reference **only** the Prometheus metrics that `libs/py/documind_core/` actually emits (circuit breaker state + failures, retrieval quality, CCB interrupts/warnings, token breaker rejects, agent stops, ingest chunk decisions, obs breaker skips). If a panel is empty when you import this, the corresponding code path hasn't executed yet — not a dashboard bug.

## Previously shipped `slo-burn.json` — REMOVED

The earlier SLO burn-rate dashboard referenced `http_requests_total`, `http_request_duration_seconds_bucket`, and `documind_eval_faithfulness` — none of which any service in this repo emits today. It was cargo-culted from a real SLO dashboard without verifying the metric producers existed.

It will come back once:

1. OpenTelemetry FastAPI auto-instrumentation is actually running in prod (the code path exists; the stack has never been started), producing `http_server_request_duration_seconds` (OTel) or `http_requests_total` (Prom exporter).
2. evaluation-svc writes `documind_eval_*` gauges after each run.

Until then, shipping a dashboard for those metrics would be misleading.
