import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


class OpenTelemetrySDK:
    def configure(self, service_name: str = "enterprise-ai-os"):
        trace.set_tracer_provider(TracerProvider())

        exporter = OTLPSpanExporter(
            endpoint=os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://localhost:4318/v1/traces"
            )
        )

        processor = BatchSpanProcessor(exporter)

        trace.get_tracer_provider().add_span_processor(processor)

        return trace.get_tracer(service_name)
