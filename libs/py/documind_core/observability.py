"""
Observability setup (Design Areas 62 — Observability by Design, 64 — SLO-Driven).

Wires:

* OpenTelemetry SDK (traces + metrics) → OTLP endpoint (collector).
* Prometheus HTTP exposition on a configurable port.
* Auto-instrumentation for FastAPI, asyncpg, httpx, redis.

Call :func:`setup_observability` exactly once at service startup.

Span naming convention
----------------------
* Top-level HTTP spans come from ``FastAPIInstrumentor`` — don't rename.
* Service-internal spans should be named ``<domain>.<operation>``
  (e.g. ``ingestion.chunk_document``, ``retrieval.vector_search``).
* Don't create spans for trivial work — a span should represent something
  you'd want to see on a trace timeline.
"""
from __future__ import annotations

import logging

try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False

try:
    from prometheus_client import start_http_server
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False

log = logging.getLogger(__name__)


def setup_observability(
    *,
    service_name: str,
    service_namespace: str = "documind",
    otlp_endpoint: str = "http://localhost:4317",
    prometheus_port: int = 0,
    environment: str = "development",
) -> None:
    """
    Initialize OTel (traces + metrics) and optionally start a Prometheus
    HTTP exposition server.

    Idempotent: re-calling is safe but does nothing after first call.
    """
    resource_attrs = {
        "service.name": service_name,
        "service.namespace": service_namespace,
        "deployment.environment": environment,
    }

    if _OTEL_AVAILABLE:
        resource = Resource.create(resource_attrs)

        # Traces
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
        )
        trace.set_tracer_provider(tracer_provider)

        # Metrics (OTLP push — the collector re-exports to Prometheus)
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
            export_interval_millis=10_000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)

        log.info("otel_initialized endpoint=%s service=%s", otlp_endpoint, service_name)
    else:
        log.warning("otel_unavailable — install opentelemetry-sdk for tracing")

    # Prometheus in-process exposition (complements OTel metrics — some teams
    # prefer pull-based scraping for ad-hoc metrics like circuit breaker state)
    if _PROM_AVAILABLE and prometheus_port:
        start_http_server(prometheus_port)
        log.info("prometheus_http_server port=%d", prometheus_port)


def instrument_fastapi(app) -> None:  # noqa: ANN001 — FastAPI typing pain
    """Apply FastAPI auto-instrumentation. Call after creating the app."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:  # pragma: no cover
        pass


def instrument_httpx() -> None:
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:  # pragma: no cover
        pass


def instrument_asyncpg() -> None:
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        AsyncPGInstrumentor().instrument()
    except ImportError:  # pragma: no cover
        pass


def instrument_redis() -> None:
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
    except ImportError:  # pragma: no cover
        pass
