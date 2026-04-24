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

from .breakers import ObservabilityCircuitBreaker

log = logging.getLogger(__name__)

# Module-level breaker protecting the OTLP export path. Inverted polarity:
# when open, export is SKIPPED — never raises, never blocks the request.
# Shared across every call site; concurrent readers are fine because the
# breaker uses an asyncio Lock internally for state transitions.
obs_breaker = ObservabilityCircuitBreaker(
    "otlp-export", failure_threshold=3, recovery_timeout=30.0,
)


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

        # Wrap the OTLP span exporter with the observability breaker so a
        # dead collector never blocks the request path. We subclass the
        # exporter's export() method rather than patching globally.
        span_exporter = _BreakerGuardedSpanExporter(
            OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True),
            breaker=obs_breaker,
        )

        # Traces
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # Metrics (OTLP push — the collector re-exports to Prometheus).
        # Metric export is already non-blocking (periodic reader), so the
        # breaker is applied at the exporter level too for uniformity.
        metric_exporter = _BreakerGuardedMetricExporter(
            OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
            breaker=obs_breaker,
        )
        reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=10_000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)

        log.info(
            "otel_initialized endpoint=%s service=%s breaker=%s",
            otlp_endpoint, service_name, obs_breaker.name,
        )
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


# ---------------------------------------------------------------------------
# Breaker-guarded exporters — inverted polarity (export skipped when open).
# ---------------------------------------------------------------------------

if _OTEL_AVAILABLE:
    from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class _BreakerGuardedSpanExporter(SpanExporter):
        """Wraps an OTLPSpanExporter; silently skips when breaker is open."""

        def __init__(self, inner: SpanExporter, *, breaker: ObservabilityCircuitBreaker) -> None:
            self._inner = inner
            self._breaker = breaker

        def export(self, spans):  # noqa: ANN001 — OTel typing
            if not self._breaker.allow_export():
                return SpanExportResult.SUCCESS  # claim success so the SDK doesn't retry-loop
            try:
                result = self._inner.export(spans)
                self._breaker.record_result(success=(result == SpanExportResult.SUCCESS))
                return result
            except Exception:
                self._breaker.record_result(success=False)
                # NEVER raise — observability must not break the app.
                return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            self._inner.shutdown()

        def force_flush(self, timeout_millis: int = 30_000) -> bool:
            if not self._breaker.allow_export():
                return True
            try:
                return self._inner.force_flush(timeout_millis)
            except Exception:
                self._breaker.record_result(success=False)
                return True

    class _BreakerGuardedMetricExporter(MetricExporter):
        """Wraps an OTLPMetricExporter; silently skips when breaker is open."""

        def __init__(self, inner: MetricExporter, *, breaker: ObservabilityCircuitBreaker) -> None:
            # Do NOT call super().__init__() — it wants preferences we're not overriding.
            self._inner = inner
            self._breaker = breaker

        @property
        def _preferred_temporality(self):  # noqa: ANN201 — OTel typing
            return self._inner._preferred_temporality  # type: ignore[attr-defined]

        def export(self, metrics_data, timeout_millis=10_000, **kwargs):  # noqa: ANN001
            if not self._breaker.allow_export():
                return MetricExportResult.SUCCESS
            try:
                result = self._inner.export(metrics_data, timeout_millis=timeout_millis, **kwargs)
                self._breaker.record_result(
                    success=(result == MetricExportResult.SUCCESS)
                )
                return result
            except Exception:
                self._breaker.record_result(success=False)
                return MetricExportResult.SUCCESS

        def force_flush(self, timeout_millis=10_000):
            if not self._breaker.allow_export():
                return True
            try:
                return self._inner.force_flush(timeout_millis)
            except Exception:
                self._breaker.record_result(success=False)
                return True

        def shutdown(self, timeout_millis=30_000, **kwargs):
            self._inner.shutdown(timeout_millis=timeout_millis, **kwargs)
else:
    # Stubs so callers don't crash if opentelemetry isn't installed.
    class _BreakerGuardedSpanExporter:  # type: ignore[no-redef]
        def __init__(self, *_a, **_k):
            pass

    class _BreakerGuardedMetricExporter:  # type: ignore[no-redef]
        def __init__(self, *_a, **_k):
            pass
