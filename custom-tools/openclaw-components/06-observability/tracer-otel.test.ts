import { describe, it, expect } from "vitest";
import { Tracer } from "./tracer";
import { AlwaysOnSampler } from "./sampler";
import { InMemoryTraceSink } from "./sinks";
import { OpenTelemetryTraceSink, OtelSpanRecord } from "./otel-trace-sink";
import { formatTraceparent, parseTraceparent } from "./trace-context";

describe("Iter 105 - W3C trace context and OTel sink boundary", () => {
  it("emits W3C trace identity on every sampled span", () => {
    const sink = new InMemoryTraceSink();
    const tracer = new Tracer(new AlwaysOnSampler(), sink);

    const span = tracer.startSpan("agent.plan", { tenantId: "t" });
    expect(parseTraceparent(span.traceparent)).toBeDefined();
    span.end("ok");

    const record = sink.list()[0];
    expect(record.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(record.spanId).toMatch(/^[0-9a-f]{16}$/);
    expect(record.parentSpanId).toBeUndefined();
    expect(record.traceparent).toBe(
      `00-${record.traceId}-${record.spanId}-01`,
    );
  });

  it("continues a valid incoming traceparent and records parentSpanId", () => {
    const sink = new InMemoryTraceSink();
    const tracer = new Tracer(new AlwaysOnSampler(), sink);
    const parent = {
      version: "00" as const,
      traceId: "4bf92f3577b34da6a3ce929d0e0e4736",
      spanId: "00f067aa0ba902b7",
      sampled: true,
    };

    tracer.startSpan("tool.dispatch", {}, {
      parentTraceparent: formatTraceparent(parent),
    }).end("ok");

    const record = sink.list()[0];
    expect(record.traceId).toBe(parent.traceId);
    expect(record.parentSpanId).toBe(parent.spanId);
    expect(record.spanId).not.toBe(parent.spanId);
    expect(parseTraceparent(record.traceparent)?.traceId).toBe(parent.traceId);
  });

  it("OpenTelemetryTraceSink maps SpanRecord into an OTel-shaped exporter payload", () => {
    const exported: OtelSpanRecord[] = [];
    const sink = new OpenTelemetryTraceSink({
      exportSpan(span) {
        exported.push(span);
      },
    });

    new Tracer(new AlwaysOnSampler(), sink)
      .startSpan("rag.retrieve", { tenantId: "tenant-A" })
      .end("error", { error: "boom" });

    expect(exported.length).toBe(1);
    expect(exported[0].name).toBe("rag.retrieve");
    expect(exported[0].traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(exported[0].spanId).toMatch(/^[0-9a-f]{16}$/);
    expect(exported[0].traceparent).toContain(exported[0].traceId);
    expect(exported[0].status).toBe("error");
    expect(exported[0].attributes).toEqual({ tenantId: "tenant-A" });
    expect(exported[0].events).toEqual({ error: "boom" });
  });
});
