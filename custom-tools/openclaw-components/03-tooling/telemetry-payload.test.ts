// Negative drills for Iter 82 (2026-05-18): Component 3 Telemetry
// payload contract. Mirrors iter 78 (ExplainabilityRecorder) +
// iter 80 (Component 6 Tracer) schema-fingerprint pattern.

import { describe, it, expect, vi } from "vitest";
import { Telemetry } from "./telemetry";

const TEL = new Telemetry();

function captureSpan(name: string, attrs: Record<string, unknown>,
                     extra: Record<string, unknown> = {}): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    const span = TEL.startSpan(name, attrs);
    span.end(extra);
    expect(log.mock.calls.length).toBe(1);
    return JSON.parse(log.mock.calls[0][0] as string) as Record<string, unknown>;
  } finally {
    log.mockRestore();
  }
}

function captureMetric(name: string, value: number,
                       tags: Record<string, string>): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    TEL.recordMetric(name, value, tags);
    expect(log.mock.calls.length).toBe(1);
    return JSON.parse(log.mock.calls[0][0] as string) as Record<string, unknown>;
  } finally {
    log.mockRestore();
  }
}

describe("Iter 82 — Telemetry span payload contract (P2)", () => {
  it("BACKDOOR: span payload carries canonical 6-field set", () => {
    const p = captureSpan("op.test", { tenantId: "t" });
    expect(p.type).toBe("trace");
    expect(p.span).toBe("op.test");
    expect(typeof p.durationMs).toBe("number");
    expect(p.attributes).toEqual({ tenantId: "t" });
    expect(p.extra).toEqual({});
    expect(typeof p.timestamp).toBe("string");
  });

  it("BACKDOOR: span EXACT key set (schema fingerprint)", () => {
    const p = captureSpan("op.fp", {});
    const keys = Object.keys(p).sort();
    expect(keys).toEqual(
      ["attributes", "durationMs", "extra", "span", "timestamp", "type"].sort(),
    );
  });

  it("span payload single-line JSON", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      TEL.startSpan("x", {}).end();
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("durationMs is non-negative", () => {
    const p = captureSpan("op.dur", {});
    expect(p.durationMs as number).toBeGreaterThanOrEqual(0);
  });

  it("timestamp is parseable ISO-8601", () => {
    const p = captureSpan("op.ts", {});
    const d = new Date(p.timestamp as string);
    expect(d.toISOString()).toBe(p.timestamp);
  });

  it("end() called twice emits TWO records (no batching/dedup)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const s = TEL.startSpan("x", {});
      s.end();
      s.end();
      expect(log.mock.calls.length).toBe(2);
    } finally {
      log.mockRestore();
    }
  });
});

describe("Iter 82 — Telemetry metric payload contract (P2)", () => {
  it("BACKDOOR: metric payload canonical 5-field set", () => {
    const p = captureMetric("requests_total", 42, { tool: "calc" });
    expect(p.type).toBe("metric");
    expect(p.name).toBe("requests_total");
    expect(p.value).toBe(42);
    expect(p.tags).toEqual({ tool: "calc" });
    expect(typeof p.timestamp).toBe("string");
  });

  it("BACKDOOR: metric EXACT key set (schema fingerprint)", () => {
    const p = captureMetric("m", 1, {});
    const keys = Object.keys(p).sort();
    expect(keys).toEqual(["name", "tags", "timestamp", "type", "value"].sort());
  });

  it("metric value of 0 is preserved (not dropped as falsy)", () => {
    const p = captureMetric("counter_total", 0, {});
    expect(p.value).toBe(0);
  });

  it("negative metric value preserved (counters may be deltas)", () => {
    const p = captureMetric("delta", -3, {});
    expect(p.value).toBe(-3);
  });

  it("empty tags object is preserved (not omitted)", () => {
    const p = captureMetric("m", 1, {});
    expect(p.tags).toEqual({});
    expect((p as Record<string, unknown>).tags).not.toBeUndefined();
  });

  it("metric payload single-line JSON", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      TEL.recordMetric("m", 1, {});
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });
});
