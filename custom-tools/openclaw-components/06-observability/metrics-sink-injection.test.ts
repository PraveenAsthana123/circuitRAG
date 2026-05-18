// Negative drills for M2.2 (2026-05-18): MetricsRecorder sink
// injection. Mirrors M2.1 pattern for the metrics surface.

import { describe, it, expect, vi } from "vitest";
import { MetricsRecorder } from "./metrics";
import {
  ConsoleMetricsSink,
  InMemoryMetricsSink,
  MetricsSink,
  MetricRecord,
} from "./sinks";

describe("M2.2 — MetricsRecorder sink injection (P1)", () => {
  it("BACKDOOR: default sink emits to console (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new MetricsRecorder().counter("m", 1, {});
      expect(log.mock.calls.length).toBe(1);
      const p = JSON.parse(log.mock.calls[0][0] as string);
      expect(p.type).toBe("metric");
      expect(p.metricType).toBe("counter");
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected InMemorySink captures; console silent", () => {
    const sink = new InMemoryMetricsSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const r = new MetricsRecorder({}, sink);
      r.counter("requests_total", 5, { tool: "calc" });
      r.histogram("latency_ms", 120, { tool: "calc" });

      expect(sink.size()).toBe(2);
      expect(sink.list()[0].name).toBe("requests_total");
      expect(sink.list()[0].metricType).toBe("counter");
      expect(sink.list()[1].name).toBe("latency_ms");
      expect(sink.list()[1].metricType).toBe("histogram");
      expect(log.mock.calls.length).toBe(0);  // sink captured it all
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: cardinality overflow STILL routes to _overflow (regression)", () => {
    const sink = new InMemoryMetricsSink();
    const r = new MetricsRecorder({ maxSeriesPerMetric: 2 }, sink);
    r.counter("m", 1, { t: "a" });
    r.counter("m", 1, { t: "b" });
    r.counter("m", 1, { t: "c" });  // overflow

    expect(sink.list()[2].labels).toEqual({ _overflow: "true" });
  });

  it("BACKDOOR: forbidden labels STILL dropped + warned (regression)", () => {
    const sink = new InMemoryMetricsSink();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const r = new MetricsRecorder({}, sink);
      r.counter("requests_total", 1, { tool: "calc", userId: "u-1" });
      // userId stripped from labels.
      expect(sink.list()[0].labels).toEqual({ tool: "calc" });
      // Warning emitted.
      const warns = warn.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "metric_forbidden_label_dropped");
      expect(warns.length).toBe(1);
    } finally {
      warn.mockRestore();
    }
  });

  it("InMemoryMetricsSink.list returns defensive copies", () => {
    const sink = new InMemoryMetricsSink();
    new MetricsRecorder({}, sink).counter("m", 1, { t: "a" });
    const list = sink.list();
    list[0].name = "MUTATED";
    expect(sink.list()[0].name).toBe("m");
  });

  it("InMemoryMetricsSink: maxRecords FIFO cap", () => {
    const sink = new InMemoryMetricsSink(3);
    const r = new MetricsRecorder({}, sink);
    for (let i = 0; i < 10; i++) {
      r.counter("m", i, { idx: String(i) });
    }
    expect(sink.size()).toBe(3);
    expect(sink.list().map((rec) => rec.value)).toEqual([7, 8, 9]);
  });

  it("custom sink routes to arbitrary consumer (extension point)", () => {
    const captured: MetricRecord[] = [];
    class RoutingSink implements MetricsSink {
      emit(r: MetricRecord): void { captured.push(r); }
    }
    new MetricsRecorder({}, new RoutingSink()).counter("c", 42, {});
    expect(captured.length).toBe(1);
    expect(captured[0].value).toBe(42);
  });

  it("ConsoleMetricsSink emits single-line JSON", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ConsoleMetricsSink().emit({
        type: "metric", metricType: "counter",
        name: "n", value: 1, labels: {},
        timestamp: new Date().toISOString(),
      });
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("metric payload schema preserved via sink (regression iter 82+92)", () => {
    const sink = new InMemoryMetricsSink();
    new MetricsRecorder({}, sink).counter("requests_total", 42, { tool: "x" });
    const r = sink.list()[0];
    const keys = Object.keys(r).sort();
    expect(keys).toEqual(
      ["labels", "metricType", "name", "timestamp", "type", "value"].sort(),
    );
  });

  it("zero-value counter preserved (not dropped as falsy) via sink", () => {
    const sink = new InMemoryMetricsSink();
    new MetricsRecorder({}, sink).counter("c", 0, {});
    expect(sink.list()[0].value).toBe(0);
  });
});
