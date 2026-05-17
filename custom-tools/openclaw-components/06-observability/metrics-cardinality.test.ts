// Negative drills for Iter 47 (2026-05-17): MetricsRecorder
// cardinality limit + forbidden-label drop.

import { describe, it, expect, vi } from "vitest";
import { MetricsRecorder } from "./metrics";

describe("MetricsRecorder — cardinality limits (P1)", () => {
  it("under budget: every label set creates a series", () => {
    const m = new MetricsRecorder({ maxSeriesPerMetric: 10 });
    for (let i = 0; i < 5; i++) {
      m.counter("op_total", 1, { component: `c${i}` });
    }
    expect(m.seriesCount("op_total")).toBe(5);
  });

  it("BACKDOOR CHECK: over-budget series route to _overflow", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const m = new MetricsRecorder({ maxSeriesPerMetric: 3 });
    for (let i = 0; i < 10; i++) {
      m.counter("op_total", 1, { user: `u${i}` });
    }
    // First 3 distinct label sets create real series, next 7 → _overflow.
    expect(m.seriesCount("op_total")).toBe(3);
    // Overflow warning fires exactly once per metric.
    const warnCalls = warn.mock.calls
      .map((c) => JSON.parse(c[0] as string))
      .filter((p) => p.type === "metric_cardinality_overflow");
    expect(warnCalls.length).toBe(1);
    expect(warnCalls[0].name).toBe("op_total");
    // The emitted metric for an overflow series has labels = { _overflow: "true" }.
    const overflowEmissions = log.mock.calls
      .map((c) => JSON.parse(c[0] as string))
      .filter((p) => p.labels?._overflow === "true");
    expect(overflowEmissions.length).toBeGreaterThan(0);
    log.mockRestore(); warn.mockRestore();
  });

  it("forbidden high-cardinality labels are dropped + logged once", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const m = new MetricsRecorder();
    // userId is in FORBIDDEN_HIGH_CARD_LABELS.
    m.counter("op_total", 1, { component: "x", userId: "u1" });
    m.counter("op_total", 1, { component: "x", userId: "u2" });
    m.counter("op_total", 1, { component: "x", userId: "u3" });

    // Emitted labels must NOT include userId.
    for (const call of log.mock.calls) {
      const p = JSON.parse(call[0] as string);
      expect(p.labels).not.toHaveProperty("userId");
    }
    // Warning fires once per (metric, forbidden-label) pair.
    const warns = warn.mock.calls
      .map((c) => JSON.parse(c[0] as string))
      .filter((p) => p.type === "metric_forbidden_label_dropped");
    expect(warns.length).toBe(1);
    expect(warns[0].label).toBe("userId");
    log.mockRestore(); warn.mockRestore();
  });

  it("metrics with same name across different recorders have independent budgets", () => {
    const m1 = new MetricsRecorder({ maxSeriesPerMetric: 2 });
    const m2 = new MetricsRecorder({ maxSeriesPerMetric: 2 });
    for (let i = 0; i < 5; i++) m1.counter("x", 1, { i: `${i}` });
    for (let i = 0; i < 5; i++) m2.counter("x", 1, { i: `${i}` });
    expect(m1.seriesCount("x")).toBe(2);
    expect(m2.seriesCount("x")).toBe(2);
  });

  it("custom forbidden-labels set works", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const m = new MetricsRecorder({
      forbiddenLabels: new Set(["secretToken"]),
    });
    // userId is allowed here because it's not in our custom set.
    m.counter("x", 1, { userId: "u", secretToken: "sk-abc" });
    const p = JSON.parse(log.mock.calls[0][0] as string);
    expect(p.labels.userId).toBe("u");
    expect(p.labels).not.toHaveProperty("secretToken");
    log.mockRestore(); warn.mockRestore();
  });
});
