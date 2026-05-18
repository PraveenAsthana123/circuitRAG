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
//     This is still console.log emission, not real OTel. The
//     sampling shape mirrors OTel's TraceIdRatioBased so the swap
//     is mechanical.

import { Sampler, AlwaysOnSampler } from "./sampler";
import { TraceSink, ConsoleTraceSink } from "./sinks";

export class Tracer {
  private readonly sink: TraceSink;
  constructor(
    private readonly sampler: Sampler = new AlwaysOnSampler(),
    // Iter M2.1 (2026-05-18): pluggable sink — pre-fix the Tracer
    // hardcoded console.log emission, blocking any test capture
    // and any real OTel/Prometheus exporter integration.
    // Default ConsoleTraceSink preserves backcompat behavior;
    // InMemoryTraceSink lets drills capture without spy boilerplate;
    // a future OTelSpanSink plugs in here unchanged.
    sink?: TraceSink,
  ) {
    this.sink = sink ?? new ConsoleTraceSink();
  }

  startSpan(name: string, attributes: Record<string, unknown>) {
    const startedAt = Date.now();
    const sampledAtStart = this.sampler.shouldSample(name, attributes);

    return {
      end: (status: "ok" | "error", extra: Record<string, unknown> = {}) => {
        const shouldEmit =
          sampledAtStart ||
          (status === "error" && this.sampler.alwaysSampleOnError());
        if (!shouldEmit) return;

        this.sink.emit({
          type: "trace",
          spanName: name,
          status,
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
