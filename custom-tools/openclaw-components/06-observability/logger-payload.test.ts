// Negative drills for Iter 89 (2026-05-18): Logger payload contract
// (schema-fingerprint). Mirrors iter 78/80/82/87 pattern.
//
// Logger has 7 behavior tests; this adds the schema fingerprint
// for both StructuredLogger.log() (open-schema) and the wrapped
// RequestLogger pattern (correlation-bound).

import { describe, it, expect, vi } from "vitest";
import { StructuredLogger, RequestLogger } from "./logger";

function captureBase(level: "info" | "warn" | "error",
                    msg: string,
                    meta: Record<string, unknown> = {}): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    new StructuredLogger().log(level, msg, meta);
    expect(log.mock.calls.length).toBe(1);
    return JSON.parse(log.mock.calls[0][0] as string);
  } finally {
    log.mockRestore();
  }
}

function captureRequest(
  call: "info" | "warn" | "error",
  msg: string,
  extra: Record<string, unknown> = {},
  correlation: Partial<Record<string, string>> = {},
): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    const rl = new RequestLogger(new StructuredLogger(), {
      requestId: "r-1", tenantId: "t-1",
      ...correlation,
    } as never);
    rl[call](msg, extra);
    expect(log.mock.calls.length).toBe(1);
    return JSON.parse(log.mock.calls[0][0] as string);
  } finally {
    log.mockRestore();
  }
}

describe("Iter 89 — Logger payload contract (P2)", () => {
  it("BACKDOOR: bare StructuredLogger.log payload carries 3 canonical fields", () => {
    const p = captureBase("info", "hi");
    expect(p.level).toBe("info");
    expect(p.message).toBe("hi");
    expect(typeof p.timestamp).toBe("string");
  });

  it("BACKDOOR: bare-log EXACT key set when no meta (schema fingerprint)", () => {
    const p = captureBase("info", "hi");
    expect(Object.keys(p).sort()).toEqual(["level", "message", "timestamp"].sort());
  });

  it("level enum: info / warn / error all accepted and preserved", () => {
    expect((captureBase("info", "x")).level).toBe("info");
    expect((captureBase("warn", "x")).level).toBe("warn");
    expect((captureBase("error", "x")).level).toBe("error");
  });

  it("meta fields ARE spread at the top level (not nested under `meta`)", () => {
    const p = captureBase("info", "x", { foo: "bar", n: 42 });
    expect(p.foo).toBe("bar");
    expect(p.n).toBe(42);
    expect(p.meta).toBeUndefined();
  });

  it("BACKDOOR: invalid requestId surfaces _requestId_invalid flag (regression)", () => {
    const p = captureBase("info", "x", { requestId: "" });
    expect(p._requestId_invalid).toBe(true);
    // Original empty value still passes through (flag is in addition).
    expect(p.requestId).toBe("");
  });

  it("BACKDOOR: invalid tenantId surfaces _tenantId_invalid flag", () => {
    const p = captureBase("info", "x", { tenantId: 123 as unknown as string });
    expect(p._tenantId_invalid).toBe(true);
  });

  it("RequestLogger payload includes all bound correlation fields", () => {
    const p = captureRequest("info", "hi", {}, {
      traceId: "tr-1", sessionId: "s-1", userId: "u-1", component: "comp",
    });
    expect(p.requestId).toBe("r-1");
    expect(p.tenantId).toBe("t-1");
    expect(p.traceId).toBe("tr-1");
    expect(p.sessionId).toBe("s-1");
    expect(p.userId).toBe("u-1");
    expect(p.component).toBe("comp");
  });

  it("RequestLogger per-call extra fields merge with correlation", () => {
    const p = captureRequest("info", "hi", { latencyMs: 50, op: "x" });
    expect(p.requestId).toBe("r-1");  // correlation preserved
    expect(p.latencyMs).toBe(50);     // extra merged
    expect(p.op).toBe("x");
  });

  it("payload is single-line newline-free JSON (log shipper safety)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new StructuredLogger().log("info", "x");
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("timestamp is parseable ISO-8601 within 5s of now", () => {
    const p = captureBase("info", "x");
    const d = new Date(p.timestamp as string);
    expect(d.toISOString()).toBe(p.timestamp);
    expect(Math.abs(d.getTime() - Date.now())).toBeLessThan(5000);
  });

  it("RequestLogger.error level surfaces in payload (no level-collapsing)", () => {
    const p = captureRequest("error", "fail");
    expect(p.level).toBe("error");
  });
});
