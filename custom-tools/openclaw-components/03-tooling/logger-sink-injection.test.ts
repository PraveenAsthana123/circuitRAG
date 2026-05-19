// Negative drills for Iter 101 (2026-05-18): Component 3 Logger
// sink injection. Uppercase-level shape (INFO/WARN/ERROR) distinct
// from Component 6 StructuredLogger's lowercase enum, so reuses
// EventSink + StreamRoutedEventSink (iter 99 pattern) rather than
// LogSink (M3.1).

import { describe, it, expect, vi } from "vitest";
import { Logger } from "./logger";
import {
  EventSink,
  EventRecord,
  InMemoryEventSink,
} from "../06-observability/sinks";

describe("Iter 101 — Component 3 Logger sink injection (P1)", () => {
  it("BACKDOOR: default routes info → console.log (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new Logger().info("hi");
      expect(log.mock.calls.length).toBe(1);
      const p = JSON.parse(log.mock.calls[0][0] as string);
      expect(p.level).toBe("INFO");
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: default routes warn → console.warn", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      new Logger().warn("slow");
      expect(warn.mock.calls.length).toBe(1);
      const p = JSON.parse(warn.mock.calls[0][0] as string);
      expect(p.level).toBe("WARN");
    } finally {
      warn.mockRestore();
    }
  });

  it("BACKDOOR: default routes error → console.error", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      new Logger().error("blew up");
      expect(err.mock.calls.length).toBe(1);
      const p = JSON.parse(err.mock.calls[0][0] as string);
      expect(p.level).toBe("ERROR");
    } finally {
      err.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures all 3 levels; consoles silent", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const l = new Logger(sink);
      l.info("a");
      l.warn("b");
      l.error("c");
      expect(sink.size()).toBe(3);
      expect(sink.list().map((r) => r.level)).toEqual(["INFO", "WARN", "ERROR"]);
      expect(log.mock.calls.length).toBe(0);
      expect(warn.mock.calls.length).toBe(0);
      expect(err.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
      warn.mockRestore();
      err.mockRestore();
    }
  });

  it("BACKDOOR: uppercase level preserved (INFO/WARN/ERROR — distinct from Component 6 lowercase)", () => {
    const sink = new InMemoryEventSink();
    const l = new Logger(sink);
    l.info("x");
    l.warn("x");
    l.error("x");
    expect(sink.list()[0].level).toBe("INFO");
    expect(sink.list()[1].level).toBe("WARN");
    expect(sink.list()[2].level).toBe("ERROR");
    // NOT lowercase — different contract than Component 6 LogSink.
    for (const r of sink.list()) {
      expect(r.level).not.toBe(String(r.level).toLowerCase());
    }
  });

  it("meta fields merge at top level (not nested)", () => {
    const sink = new InMemoryEventSink();
    new Logger(sink).info("x", { foo: "bar", n: 42 });
    const r = sink.list()[0];
    expect(r.foo).toBe("bar");
    expect(r.n).toBe(42);
    expect(r.meta).toBeUndefined();
  });

  it("custom sink can route to a unified audit consumer", () => {
    const captured: EventRecord[] = [];
    class UnifiedSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const l = new Logger(new UnifiedSink());
    l.info("x");
    l.error("y");
    expect(captured.length).toBe(2);
    expect(captured[0].level).toBe("INFO");
    expect(captured[1].level).toBe("ERROR");
  });

  it("custom sink sees _stream hint (StreamRouted strips it)", () => {
    const sink = new InMemoryEventSink();
    new Logger(sink).warn("hint");
    expect(sink.list()[0]._stream).toBe("warn");
  });

  it("StreamRoutedEventSink (default) strips _stream from console emissions", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      new Logger().warn("stripped");
      const payload = JSON.parse(warn.mock.calls[0][0] as string);
      expect(payload._stream).toBeUndefined();
    } finally {
      warn.mockRestore();
    }
  });

  it("single-line JSON contract preserved on every level", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const l = new Logger();
      l.info("a");
      l.warn("b");
      l.error("c");
      const allCalls = [...log.mock.calls, ...warn.mock.calls, ...err.mock.calls];
      for (const call of allCalls) {
        expect((call[0] as string)).not.toContain("\n");
      }
    } finally {
      log.mockRestore();
      warn.mockRestore();
      err.mockRestore();
    }
  });

  it("timestamp is parseable ISO-8601", () => {
    const sink = new InMemoryEventSink();
    new Logger(sink).info("x");
    const ts = sink.list()[0].timestamp as string;
    const d = new Date(ts);
    expect(d.toISOString()).toBe(ts);
  });
});
