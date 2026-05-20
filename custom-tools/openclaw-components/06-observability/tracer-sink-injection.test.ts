// Negative drills for M2.1 (2026-05-18): Tracer sink injection.
// Locks the seam where real OTel / Prometheus span exporters will
// plug in. Default ConsoleTraceSink preserves backcompat; injected
// InMemoryTraceSink lets drills capture without spy boilerplate.

import { describe, it, expect, vi } from "vitest";
import { Tracer } from "./tracer";
import { AlwaysOnSampler } from "./sampler";
import {
  ConsoleTraceSink,
  InMemoryTraceSink,
  TraceSink,
  SpanRecord,
} from "./sinks";

describe("M2.1 — Tracer sink injection (P1)", () => {
  it("BACKDOOR: default sink (no override) emits to console (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new Tracer(new AlwaysOnSampler()).startSpan("op", {}).end("ok");
      expect(log.mock.calls.length).toBe(1);
      const payload = JSON.parse(log.mock.calls[0][0] as string);
      expect(payload.type).toBe("trace");
      expect(payload.spanName).toBe("op");
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected InMemoryTraceSink captures emissions instead of console", () => {
    const sink = new InMemoryTraceSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const tracer = new Tracer(new AlwaysOnSampler(), sink);
      tracer.startSpan("op-1", { tenantId: "t" }).end("ok");
      tracer.startSpan("op-2", {}).end("error");

      expect(sink.size()).toBe(2);
      expect(sink.list()[0].spanName).toBe("op-1");
      expect(sink.list()[1].spanName).toBe("op-2");
      expect(sink.list()[1].status).toBe("error");
      // NOTHING went to console.
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: dropped span (not sampled, not error) emits NOTHING to sink either", () => {
    class NeverSampler {
      shouldSample(): boolean { return false; }
      alwaysSampleOnError(): boolean { return false; }
    }
    const sink = new InMemoryTraceSink();
    const tracer = new Tracer(new NeverSampler(), sink);
    tracer.startSpan("op", {}).end("ok");
    expect(sink.size()).toBe(0);
  });

  it("InMemoryTraceSink.list returns defensive copies (no mutation leak)", () => {
    const sink = new InMemoryTraceSink();
    new Tracer(new AlwaysOnSampler(), sink).startSpan("op", { x: 1 }).end("ok");

    const list = sink.list();
    list[0].spanName = "MUTATED";
    expect(sink.list()[0].spanName).toBe("op");
  });

  it("InMemoryTraceSink: maxRecords FIFO cap (memory-bound)", () => {
    const sink = new InMemoryTraceSink(3);
    const tracer = new Tracer(new AlwaysOnSampler(), sink);
    for (let i = 0; i < 10; i++) {
      tracer.startSpan(`op-${i}`, {}).end("ok");
    }
    expect(sink.size()).toBe(3);
    // Oldest dropped; newest retained.
    expect(sink.list().map((r) => r.spanName))
      .toEqual(["op-7", "op-8", "op-9"]);
  });

  it("InMemoryTraceSink: maxRecords=1 edge (each emit evicts previous)", () => {
    const sink = new InMemoryTraceSink(1);
    const tracer = new Tracer(new AlwaysOnSampler(), sink);
    tracer.startSpan("first", {}).end("ok");
    tracer.startSpan("second", {}).end("ok");
    expect(sink.size()).toBe(1);
    expect(sink.list()[0].spanName).toBe("second");
  });

  it("InMemoryTraceSink constructor rejects sub-1 maxRecords", () => {
    expect(() => new InMemoryTraceSink(0)).toThrow(/maxRecords/);
    expect(() => new InMemoryTraceSink(-1)).toThrow(/maxRecords/);
  });

  it("InMemoryTraceSink.clear empties the buffer", () => {
    const sink = new InMemoryTraceSink();
    new Tracer(new AlwaysOnSampler(), sink).startSpan("op", {}).end("ok");
    expect(sink.size()).toBe(1);
    sink.clear();
    expect(sink.size()).toBe(0);
    expect(sink.list()).toEqual([]);
  });

  it("custom sink can route to any consumer (extension point regression)", () => {
    // A consumer that re-emits to its own taxonomy (e.g., OTel
    // span exporter) just implements TraceSink.emit. Drill that
    // the seam is open for arbitrary subclasses.
    const captured: SpanRecord[] = [];
    class RoutingSink implements TraceSink {
      emit(r: SpanRecord): void { captured.push(r); }
    }
    new Tracer(new AlwaysOnSampler(), new RoutingSink())
      .startSpan("routed", {})
      .end("ok");
    expect(captured.length).toBe(1);
    expect(captured[0].spanName).toBe("routed");
  });

  it("ConsoleTraceSink emits single-line JSON (log-shipper safety regression)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ConsoleTraceSink().emit({
        type: "trace", spanName: "x", status: "ok",
        traceId: "4bf92f3577b34da6a3ce929d0e0e4736",
        spanId: "00f067aa0ba902b7",
        traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        durationMs: 1, attributes: {}, extra: {},
        sampled: true, sampledOnError: false,
        timestamp: new Date().toISOString(),
      });
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("payload schema preserved across sinks (regression iter 80)", () => {
    const sink = new InMemoryTraceSink();
    new Tracer(new AlwaysOnSampler(), sink)
      .startSpan("op", { tenantId: "t" })
      .end("ok", { foo: "bar" });

    const r = sink.list()[0];
    expect(r.type).toBe("trace");
    expect(r.spanName).toBe("op");
    expect(r.status).toBe("ok");
    expect(typeof r.durationMs).toBe("number");
    expect(r.attributes).toEqual({ tenantId: "t" });
    expect(r.extra).toEqual({ foo: "bar" });
    expect(typeof r.sampled).toBe("boolean");
    expect(typeof r.sampledOnError).toBe("boolean");
    expect(typeof r.timestamp).toBe("string");
  });
});
