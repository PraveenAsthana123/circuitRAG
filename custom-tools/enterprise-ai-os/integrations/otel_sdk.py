# ✅ P1 IMPROVED (Iter 43, 2026-05-17): Resource attributes + auth
#     header. Pre-fix every span emitted from any service / replica
#     looked identical — collector + downstream observability couldn't
#     tell which service produced a span, which version, which env.
#     Also: no auth header on the OTLP exporter — exposing a collector
#     to the internet without auth = trace data leak.
#
#     Now configure() sets:
#       - Resource attributes: service.name, service.version,
#         service.instance.id, deployment.environment, plus any
#         caller-supplied extras (OTEL Resource Detection convention).
#       - OTLP headers: OTEL_EXPORTER_OTLP_HEADERS env (comma-sep
#         k=v pairs, e.g. "Authorization=Bearer abc").
#
#     Resources are STATIC at provider construction — set once at
#     startup, not per-span. Real production sets them from k8s
#     downward API + image tag at build time.

import os
import uuid
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


def _parse_headers(raw: Optional[str]) -> Dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS env format: comma-separated
    `k=v` pairs. Returns {} on missing/empty. Whitespace tolerant."""
    if not raw:
        return {}
    out: Dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        out[k.strip()] = v.strip()
    return out


class OpenTelemetrySDK:
    def configure(
        self,
        service_name: str = "enterprise-ai-os",
        service_version: Optional[str] = None,
        deployment_environment: Optional[str] = None,
        extra_resource_attrs: Optional[Dict[str, Any]] = None,
    ):
        # Iter 43: build the Resource per OTel semantic conventions.
        attrs: Dict[str, Any] = {
            "service.name": service_name,
            "service.version": service_version
                or os.getenv("SERVICE_VERSION", "unknown"),
            "service.instance.id": os.getenv(
                "HOSTNAME", f"{service_name}-{uuid.uuid4()}"
            ),
            "deployment.environment": deployment_environment
                or os.getenv("DEPLOYMENT_ENV", "unknown"),
        }
        if extra_resource_attrs:
            attrs.update(extra_resource_attrs)

        resource = Resource.create(attrs)
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://localhost:4318/v1/traces",
        )
        headers = _parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS"))

        # Defensive nudge: warn if the exporter is HTTP (not HTTPS)
        # without auth header — that's a trace-data-leak risk to
        # anyone on the network path.
        if endpoint.startswith("http://") and not headers:
            # Emit a single startup log line, not on every span.
            import sys
            sys.stderr.write(
                "[OpenTelemetrySDK] WARNING: OTLP endpoint is HTTP "
                "(not HTTPS) and OTEL_EXPORTER_OTLP_HEADERS is empty "
                "— trace data is unauthenticated + unencrypted in "
                "transit. Set OTEL_EXPORTER_OTLP_HEADERS=Authorization="
                "Bearer <token> in production.\n"
            )

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        return trace.get_tracer(service_name)
