// Negative drills for Iter 42 (2026-05-17): StructuredLogger
// + RequestLogger correlation discipline.

import { describe, it, expect, vi } from "vitest";
import { StructuredLogger, RequestLogger } from "./logger";

describe("StructuredLogger (P1)", () => {
  it("emits JSON with level + message + timestamp", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    new StructuredLogger().log("info", "hi", { foo: "bar" });
    const payload = JSON.parse(log.mock.calls[0][0] as string);
    expect(payload.level).toBe("info");
    expect(payload.message).toBe("hi");
    expect(payload.foo).toBe("bar");
    expect(payload.timestamp).toBeTruthy();
    log.mockRestore();
  });

  it("BACKDOOR CHECK: invalid requestId surfaces an _invalid flag", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    new StructuredLogger().log("info", "x", { requestId: 42 } as any);
    const payload = JSON.parse(log.mock.calls[0][0] as string);
    expect(payload._requestId_invalid).toBe(true);
    log.mockRestore();
  });

  it("empty-string tenantId surfaces an _invalid flag", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    new StructuredLogger().log("info", "x", { tenantId: "" });
    const payload = JSON.parse(log.mock.calls[0][0] as string);
    expect(payload._tenantId_invalid).toBe(true);
    log.mockRestore();
  });
});

describe("RequestLogger (P1)", () => {
  it("refuses to construct without requestId", () => {
    expect(() => new RequestLogger(
      new StructuredLogger(),
      { requestId: "", tenantId: "t" },
    )).toThrow(/requestId/);
  });

  it("refuses to construct without tenantId", () => {
    expect(() => new RequestLogger(
      new StructuredLogger(),
      { requestId: "r", tenantId: "" },
    )).toThrow(/tenantId/);
  });

  it("BACKDOOR CHECK: every log line carries the correlation fields", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const rl = new RequestLogger(
      new StructuredLogger(),
      { requestId: "r1", tenantId: "t1", traceId: "tr1" },
    );
    rl.info("op start");
    rl.warn("op slow");
    rl.error("op failed");
    expect(log).toHaveBeenCalledTimes(3);
    for (const call of log.mock.calls) {
      const p = JSON.parse(call[0] as string);
      expect(p.requestId).toBe("r1");
      expect(p.tenantId).toBe("t1");
      expect(p.traceId).toBe("tr1");
    }
    log.mockRestore();
  });

  it("extra fields per-call merge with correlation", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const rl = new RequestLogger(
      new StructuredLogger(),
      { requestId: "r", tenantId: "t" },
    );
    rl.info("query", { latencyMs: 42 });
    const p = JSON.parse(log.mock.calls[0][0] as string);
    expect(p.requestId).toBe("r");
    expect(p.latencyMs).toBe(42);
    log.mockRestore();
  });
});
