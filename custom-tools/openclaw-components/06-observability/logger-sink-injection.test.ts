// Negative drills for M3.1 (2026-05-18): StructuredLogger sink
// injection. Completes the Component 6 sink-coverage (after M2.1
// Tracer, M2.2 Metrics, M2.3 EventBus).

import { describe, it, expect, vi } from "vitest";
import { StructuredLogger, RequestLogger } from "./logger";
import {
  ConsoleLogSink,
  InMemoryLogSink,
  LogSink,
  LogRecord,
} from "./sinks";

describe("M3.1 — StructuredLogger sink injection (P1)", () => {
  it("BACKDOOR: default sink emits to console (backcompat preserved)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new StructuredLogger().log("info", "hi");
      expect(log.mock.calls.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures; console silent", () => {
    const sink = new InMemoryLogSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const logger = new StructuredLogger(sink);
      logger.log("info", "first");
      logger.log("warn", "second");
      logger.log("error", "third");

      expect(sink.size()).toBe(3);
      expect(sink.list()[0].level).toBe("info");
      expect(sink.list()[0].message).toBe("first");
      expect(sink.list()[2].level).toBe("error");
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: invalid-correlation _invalid flag preserved through sink (regression iter 89)", () => {
    const sink = new InMemoryLogSink();
    new StructuredLogger(sink).log("info", "x", { requestId: "" });
    expect(sink.list()[0]._requestId_invalid).toBe(true);
  });

  it("payload schema preserved across sinks (regression iter 89)", () => {
    const sink = new InMemoryLogSink();
    new StructuredLogger(sink).log("info", "msg", { foo: "bar", n: 42 });
    const r = sink.list()[0];
    expect(r.level).toBe("info");
    expect(r.message).toBe("msg");
    expect(typeof r.timestamp).toBe("string");
    expect(r.foo).toBe("bar");
    expect(r.n).toBe(42);
  });

  it("RequestLogger uses the SAME base sink (correlation fields flow through)", () => {
    const sink = new InMemoryLogSink();
    const base = new StructuredLogger(sink);
    const rl = new RequestLogger(base, {
      requestId: "r-1", tenantId: "t-1", traceId: "tr",
    });
    rl.info("op started");
    rl.warn("op slow");
    rl.error("op failed");

    expect(sink.size()).toBe(3);
    for (const r of sink.list()) {
      expect(r.requestId).toBe("r-1");
      expect(r.tenantId).toBe("t-1");
      expect(r.traceId).toBe("tr");
    }
  });

  it("InMemoryLogSink.list returns defensive copies", () => {
    const sink = new InMemoryLogSink();
    new StructuredLogger(sink).log("info", "original");
    const list = sink.list();
    list[0].message = "MUTATED";
    expect(sink.list()[0].message).toBe("original");
  });

  it("InMemoryLogSink: maxRecords FIFO cap", () => {
    const sink = new InMemoryLogSink(3);
    const logger = new StructuredLogger(sink);
    for (let i = 0; i < 10; i++) logger.log("info", `m-${i}`);
    expect(sink.size()).toBe(3);
    expect(sink.list().map((r) => r.message)).toEqual(["m-7", "m-8", "m-9"]);
  });

  it("InMemoryLogSink constructor rejects sub-1 maxRecords", () => {
    expect(() => new InMemoryLogSink(0)).toThrow(/maxRecords/);
    expect(() => new InMemoryLogSink(-1)).toThrow(/maxRecords/);
  });

  it("custom sink routes to arbitrary consumer (extension point)", () => {
    const captured: LogRecord[] = [];
    class RoutingSink implements LogSink {
      emit(r: LogRecord): void { captured.push(r); }
    }
    new StructuredLogger(new RoutingSink()).log("error", "routed");
    expect(captured.length).toBe(1);
    expect(captured[0].level).toBe("error");
  });

  it("ConsoleLogSink emits single-line JSON (log-shipper safety)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ConsoleLogSink().emit({
        level: "info", message: "x",
        timestamp: new Date().toISOString(),
      });
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("clear() empties the buffer", () => {
    const sink = new InMemoryLogSink();
    new StructuredLogger(sink).log("info", "x");
    expect(sink.size()).toBe(1);
    sink.clear();
    expect(sink.size()).toBe(0);
  });
});
