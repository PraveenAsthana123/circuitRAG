// Negative drills for Iter 92 (2026-05-18): MetricsRecorder boundary
// + payload contract. Existing 5 tests cover headline behavior;
// this adds boundary semantics + schema-fingerprint.

import { describe, it, expect, vi } from "vitest";
import { MetricsRecorder } from "./metrics";

function captureEmit(fn: () => void): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    fn();
    expect(log.mock.calls.length).toBeGreaterThan(0);
    return JSON.parse(log.mock.calls[log.mock.calls.length - 1][0] as string);
  } finally {
    log.mockRestore();
  }
}

describe("Iter 92 — MetricsRecorder boundary + payload (P2)", () => {
  it("BOUNDARY: exactly at maxSeries — last unique label set is the LAST normal series", () => {
    const r = new MetricsRecorder({ maxSeriesPerMetric: 3 });
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      r.counter("m", 1, { tag: "a" });
      r.counter("m", 1, { tag: "b" });
      r.counter("m", 1, { tag: "c" });  // 3rd, still under limit
      // 4th unique → overflow.
      r.counter("m", 1, { tag: "d" });
      // Inspect: last emission's labels should be _overflow.
      const lastPayload = JSON.parse(log.mock.calls[3][0] as string);
      expect(lastPayload.labels).toEqual({ _overflow: "true" });
      // Third emission was still a normal label set.
      const thirdPayload = JSON.parse(log.mock.calls[2][0] as string);
      expect(thirdPayload.labels).toEqual({ tag: "c" });
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: subsequent emissions for ALREADY-SEEN labels are NORMAL (not re-overflow)", () => {
    const r = new MetricsRecorder({ maxSeriesPerMetric: 2 });
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      r.counter("m", 1, { tag: "a" });
      r.counter("m", 1, { tag: "b" });
      r.counter("m", 1, { tag: "c" });  // overflow
      // 4th emission of 'a' (already seen) — normal labels.
      r.counter("m", 1, { tag: "a" });
      const lastPayload = JSON.parse(log.mock.calls[3][0] as string);
      expect(lastPayload.labels).toEqual({ tag: "a" });  // not overflow
    } finally {
      log.mockRestore();
    }
  });

  it("metric payload canonical 6-field set", () => {
    const r = new MetricsRecorder();
    const p = captureEmit(() => r.counter("m", 42, { t: "1" }));
    expect(p.type).toBe("metric");
    expect(p.metricType).toBe("counter");
    expect(p.name).toBe("m");
    expect(p.value).toBe(42);
    expect(p.labels).toEqual({ t: "1" });
    expect(typeof p.timestamp).toBe("string");
  });

  it("BACKDOOR: metric EXACT key set (schema fingerprint)", () => {
    const r = new MetricsRecorder();
    const p = captureEmit(() => r.counter("m", 1, {}));
    const keys = Object.keys(p).sort();
    expect(keys).toEqual(
      ["labels", "metricType", "name", "timestamp", "type", "value"].sort(),
    );
  });

  it("histogram uses metricType='histogram' (not 'counter')", () => {
    const r = new MetricsRecorder();
    const p = captureEmit(() => r.histogram("latency_ms", 150, {}));
    expect(p.metricType).toBe("histogram");
  });

  it("BOUNDARY: maxSeriesPerMetric=1 allows ONE unique series, then overflow", () => {
    const r = new MetricsRecorder({ maxSeriesPerMetric: 1 });
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      r.counter("m", 1, { t: "a" });  // 1st — normal
      r.counter("m", 1, { t: "b" });  // 2nd — overflow
      const first = JSON.parse(log.mock.calls[0][0] as string);
      const second = JSON.parse(log.mock.calls[1][0] as string);
      expect(first.labels).toEqual({ t: "a" });
      expect(second.labels).toEqual({ _overflow: "true" });
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: overflow warning is logged at most ONCE per metric (no spam)", () => {
    const r = new MetricsRecorder({ maxSeriesPerMetric: 1 });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      r.counter("m", 1, { t: "a" });
      r.counter("m", 1, { t: "b" });  // 1st overflow → warn
      r.counter("m", 1, { t: "c" });  // 2nd overflow → no warn
      r.counter("m", 1, { t: "d" });  // 3rd overflow → no warn
      const overflowWarns = warn.mock.calls.filter((c) => {
        const p = JSON.parse(c[0] as string);
        return p.type === "metric_cardinality_overflow";
      });
      expect(overflowWarns.length).toBe(1);
    } finally {
      warn.mockRestore();
      log.mockRestore();
    }
  });

  it("different METRIC NAMES have independent overflow tracking", () => {
    const r = new MetricsRecorder({ maxSeriesPerMetric: 1 });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      // Metric A: trigger overflow.
      r.counter("a", 1, { t: "1" });
      r.counter("a", 1, { t: "2" });
      // Metric B: distinct cardinality budget.
      r.counter("b", 1, { t: "1" });
      r.counter("b", 1, { t: "2" });
      const overflowWarns = warn.mock.calls.map((c) =>
        JSON.parse(c[0] as string),
      ).filter((p) => p.type === "metric_cardinality_overflow");
      expect(overflowWarns.length).toBe(2);
      const names = overflowWarns.map((p) => p.name).sort();
      expect(names).toEqual(["a", "b"]);
    } finally {
      warn.mockRestore();
      log.mockRestore();
    }
  });

  it("payload is single-line newline-free JSON", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new MetricsRecorder().counter("m", 1, {});
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("empty labels object preserved (not omitted)", () => {
    const r = new MetricsRecorder();
    const p = captureEmit(() => r.counter("m", 1, {}));
    expect(p.labels).toEqual({});
  });
});
