import { SpanRecord, TraceSink } from "./sinks";

export interface OtelSpanExporter {
  exportSpan(span: OtelSpanRecord): void;
}

export interface OtelSpanRecord {
  readonly name: string;
  readonly traceId: string;
  readonly spanId: string;
  readonly parentSpanId?: string;
  readonly traceparent: string;
  readonly status: "ok" | "error";
  readonly durationMs: number;
  readonly attributes: Record<string, unknown>;
  readonly events: Record<string, unknown>;
  readonly startTimeUnixMs?: number;
  readonly endTimeUnixMs: number;
}

export class OpenTelemetryTraceSink implements TraceSink {
  constructor(private readonly exporter: OtelSpanExporter) {}

  emit(record: SpanRecord): void {
    this.exporter.exportSpan({
      name: record.spanName,
      traceId: record.traceId,
      spanId: record.spanId,
      parentSpanId: record.parentSpanId,
      traceparent: record.traceparent,
      status: record.status,
      durationMs: record.durationMs,
      attributes: record.attributes,
      events: record.extra,
      endTimeUnixMs: Date.parse(record.timestamp),
    });
  }
}
