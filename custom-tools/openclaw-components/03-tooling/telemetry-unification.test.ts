// Negative drills for Iter 106 (2026-05-18): Component 3 Telemetry
// sink unification — locks that the old ToolTelemetry* names alias
// the canonical EventSink/EventRecord types from Component 6.
// Backcompat: existing callers using old names still work; new
// code can use either name interchangeably.

import { describe, it, expect, vi } from "vitest";
import {
  Telemetry,
  ToolTelemetrySink,
  ToolTelemetryRecord,
  ConsoleToolTelemetrySink,
  InMemoryToolTelemetrySink,
} from "./telemetry";
import {
  EventSink,
  EventRecord,
  ConsoleEventSink,
  InMemoryEventSink,
} from "../06-observability/sinks";

describe("Iter 106 — Telemetry sink unification (P2)", () => {
  it("BACKDOOR: ToolTelemetrySink is an alias for EventSink (structural compat)", () => {
    // Both directions: a ToolTelemetrySink consumer accepts an EventSink
    // and vice versa.
    const eventSink: EventSink = new InMemoryEventSink();
    const asTool: ToolTelemetrySink = eventSink;
    expect(typeof asTool.emit).toBe("function");

    const toolSink: ToolTelemetrySink = new InMemoryToolTelemetrySink();
    const asEvent: EventSink = toolSink;
    expect(typeof asEvent.emit).toBe("function");
  });

  it("BACKDOOR: ToolTelemetryRecord is an alias for EventRecord", () => {
    // TS structural typing — a record typed as one accepts the other.
    const r: ToolTelemetryRecord = { type: "trace", foo: "bar" };
    const e: EventRecord = r;
    expect(e.type).toBe("trace");
  });

  it("BACKDOOR: ConsoleToolTelemetrySink extends ConsoleEventSink (subclass)", () => {
    const s = new ConsoleToolTelemetrySink();
    expect(s).toBeInstanceOf(ConsoleEventSink);
    // emit() routes to console.log (regression iter 82)
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      s.emit({ type: "trace", span: "x" });
      expect(log.mock.calls.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: InMemoryToolTelemetrySink extends InMemoryEventSink (subclass)", () => {
    const s = new InMemoryToolTelemetrySink();
    expect(s).toBeInstanceOf(InMemoryEventSink);
    s.emit({ type: "trace", span: "x" });
    s.emit({ type: "metric", name: "m" });
    expect(s.size()).toBe(2);
    expect(s.list()[0].type).toBe("trace");
    expect(s.list()[1].type).toBe("metric");
  });

  it("BACKDOOR: Telemetry can be wired with a canonical InMemoryEventSink (cross-component reuse)", () => {
    const sink = new InMemoryEventSink();
    const t = new Telemetry(sink);
    t.startSpan("op", { tenantId: "t" }).end();
    t.recordMetric("requests_total", 5, { tool: "calc" });

    expect(sink.size()).toBe(2);
    expect(sink.list()[0].type).toBe("trace");
    expect(sink.list()[1].type).toBe("metric");
  });

  it("BACKDOOR: Telemetry can be wired with the legacy InMemoryToolTelemetrySink (backcompat)", () => {
    const sink = new InMemoryToolTelemetrySink();
    const t = new Telemetry(sink);
    t.startSpan("op", {}).end();
    t.recordMetric("m", 1, {});
    expect(sink.size()).toBe(2);
  });

  it("payload schema preserved through the unified type (iter 82 regression)", () => {
    const sink = new InMemoryEventSink();
    new Telemetry(sink).startSpan("op", { a: 1 }).end({ b: 2 });
    const r = sink.list()[0];
    // Iter 82's schema-fingerprint: type, span, durationMs, timestamp,
    // attributes, extra.
    const keys = Object.keys(r).sort();
    expect(keys).toEqual(
      ["attributes", "durationMs", "extra", "span", "timestamp", "type"].sort(),
    );
  });

  it("default Telemetry (no sink arg) still works (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new Telemetry().startSpan("x", {}).end();
      expect(log.mock.calls.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("backwards-named ConsoleToolTelemetrySink still constructs and is usable", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const sink = new ConsoleToolTelemetrySink();
      new Telemetry(sink).recordMetric("m", 1, {});
      expect(log.mock.calls.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("InMemoryToolTelemetrySink defensive-copy + bounds behavior inherited from EventSink", () => {
    // Iter 92 + M2 inherited: list() returns defensive copies + FIFO cap.
    const sink = new InMemoryToolTelemetrySink(3);
    for (let i = 0; i < 10; i++) sink.emit({ type: "metric", n: i });
    expect(sink.size()).toBe(3);
    // Defensive copy: mutating list() entry doesn't affect internal.
    const list = sink.list();
    list[0].n = 999;
    expect(sink.list()[0].n).not.toBe(999);
  });
});
