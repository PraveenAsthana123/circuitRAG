// ✅ P1 IMPROVED (Iter 29, 2026-05-17): pluggable sampler.
//     Pre-fix: every span was emitted unconditionally. High-traffic
//     services would flood observability storage; low-rate failures
//     would still get drowned in success-noise.
//
//     Now: caller supplies a Sampler. ProbabilisticSampler drops
//     non-error spans by configured rate. AlwaysOnSampler keeps
//     the original (test-friendly) behavior. Errors ALWAYS emit
//     when alwaysSampleOnError() is true (default).
//
// ✅ P0 IMPROVED (Iter 105, 2026-05-19): W3C trace context.
//     Spans now carry traceId/spanId/parentSpanId/traceparent so an
//     OpenTelemetryTraceSink can export real span identity and callers
//     can propagate traceparent headers across service boundaries.

import { Sampler, AlwaysOnSampler } from "./sampler";
import { TraceSink, ConsoleTraceSink } from "./sinks";
import { createTraceContext, formatTraceparent } from "./trace-context";

export interface StartSpanOptions {
  readonly parentTraceparent?: string;
}

export interface SpanHandle {
  readonly traceparent: string;
  end(status: "ok" | "error", extra?: Record<string, unknown>): void;
}

export class Tracer {
  private readonly sink: TraceSink;
  constructor(
    private readonly sampler: Sampler = new AlwaysOnSampler(),
    // Iter M2.1 (2026-05-18): pluggable sink — pre-fix the Tracer
    // hardcoded console.log emission, blocking any test capture
    // and any real OTel/Prometheus exporter integration.
    // Default ConsoleTraceSink preserves backcompat behavior;
    // InMemoryTraceSink lets drills capture without spy boilerplate;
    // OpenTelemetryTraceSink plugs in here for exporter wiring.
    sink?: TraceSink,
  ) {
    this.sink = sink ?? new ConsoleTraceSink();
  }

  startSpan(
    name: string,
    attributes: Record<string, unknown>,
    options: StartSpanOptions = {},
  ): SpanHandle {
    const startedAt = Date.now();
    const sampledAtStart = this.sampler.shouldSample(name, attributes);
    const context = createTraceContext({
      sampled: sampledAtStart,
      parentTraceparent: options.parentTraceparent,
    });
    const traceparent = formatTraceparent(context);

    return {
      traceparent,
      end: (status: "ok" | "error", extra: Record<string, unknown> = {}) => {
        const shouldEmit =
          sampledAtStart ||
          (status === "error" && this.sampler.alwaysSampleOnError());
        if (!shouldEmit) return;

        this.sink.emit({
          type: "trace",
          spanName: name,
          status,
          traceId: context.traceId,
          spanId: context.spanId,
          parentSpanId: context.parentSpanId,
          traceparent,
          durationMs: Date.now() - startedAt,
          attributes,
          extra,
          sampled: sampledAtStart,
          sampledOnError: !sampledAtStart && status === "error",
          timestamp: new Date().toISOString(),
        });
      },
    };
  }
}
