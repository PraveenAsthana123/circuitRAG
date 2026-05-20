// Negative drills for Iter 80 (2026-05-18): Tracer payload contract.
//
// Mirrors iter 78 (ExplainabilityRecorder payload contract). The
// tracer emits one JSON log line per span end; downstream log
// shippers + tracing tools consume the payload by field name.
// Schema-fingerprint test forces deliberate review of any payload
// additions.

import { describe, it, expect, vi } from "vitest";
import { Tracer } from "./tracer";
import { AlwaysOnSampler } from "./sampler";

function captureSpan(
  name: string,
  attrs: Record<string, unknown>,
  status: "ok" | "error" = "ok",
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    const tracer = new Tracer(new AlwaysOnSampler());
    const span = tracer.startSpan(name, attrs);
    span.end(status, extra);
    expect(log.mock.calls.length).toBe(1);
    return JSON.parse(log.mock.calls[0][0] as string) as Record<string, unknown>;
  } finally {
    log.mockRestore();
  }
}

describe("Iter 80 — Tracer payload contract (P1)", () => {
  it("BACKDOOR: span payload carries the canonical field set", () => {
    const p = captureSpan("op.test", { tenantId: "t-1", requestId: "r-1" });
    expect(p.type).toBe("trace");
    expect(p.spanName).toBe("op.test");
    expect(p.status).toBe("ok");
    expect(p.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(p.spanId).toMatch(/^[0-9a-f]{16}$/);
    expect(p.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
    expect(typeof p.durationMs).toBe("number");
    expect(p.attributes).toEqual({ tenantId: "t-1", requestId: "r-1" });
    expect(p.extra).toEqual({});
    expect(p.sampled).toBe(true);
    expect(p.sampledOnError).toBe(false);
    expect(typeof p.timestamp).toBe("string");
  });

  it("BACKDOOR: payload field set EXACTLY these 12 keys + nothing more (schema fingerprint)", () => {
    const p = captureSpan("op.fingerprint", { a: 1 });
    const keys = Object.keys(p).sort();
    expect(keys).toEqual(
      ["attributes", "durationMs", "extra", "sampled", "sampledOnError",
       "spanId", "spanName", "status", "timestamp", "traceId", "traceparent", "type"].sort(),
    );
  });

  it("error span has status='error' and sampledOnError=false when already sampled", () => {
    const p = captureSpan("op.fail", { x: 1 }, "error");
    expect(p.status).toBe("error");
    expect(p.sampled).toBe(true);
    expect(p.sampledOnError).toBe(false);
  });

  it("error span sampled BECAUSE of error (alwaysSampleOnError) has sampledOnError=true", () => {
    class NeverOnButErrorSampler {
      shouldSample(): boolean { return false; }
      alwaysSampleOnError(): boolean { return true; }
    }
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const tracer = new Tracer(new NeverOnButErrorSampler());
      const span = tracer.startSpan("op.error-only", {});
      span.end("error");
      expect(log.mock.calls.length).toBe(1);
      const p = JSON.parse(log.mock.calls[0][0] as string);
      expect(p.sampled).toBe(false);
      expect(p.sampledOnError).toBe(true);
      expect(p.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-00$/);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: dropped span (not sampled, not error) emits NOTHING", () => {
    class NeverSampler {
      shouldSample(): boolean { return false; }
      alwaysSampleOnError(): boolean { return false; }
    }
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const tracer = new Tracer(new NeverSampler());
      const span = tracer.startSpan("op.dropped", {});
      span.end("ok");
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("extra fields per-call appear under `extra`, not flattened into top level", () => {
    const p = captureSpan("op.extra", {}, "ok", { customField: 42 });
    expect(p.extra).toEqual({ customField: 42 });
    expect(p.customField).toBeUndefined();
  });

  it("durationMs is non-negative", () => {
    const p = captureSpan("op.dur", {});
    expect(typeof p.durationMs).toBe("number");
    expect(p.durationMs as number).toBeGreaterThanOrEqual(0);
  });

  it("timestamp is parseable ISO-8601 within 5s of now", () => {
    const p = captureSpan("op.ts", {});
    const parsed = new Date(p.timestamp as string);
    expect(parsed.toISOString()).toBe(p.timestamp);
    expect(Math.abs(parsed.getTime() - Date.now())).toBeLessThan(5000);
  });

  it("payload is single-line newline-free JSON (log shipper safety)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const tracer = new Tracer(new AlwaysOnSampler());
      tracer.startSpan("op.line", {}).end("ok");
      const raw = log.mock.calls[0][0] as string;
      expect(raw).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });
});
