// Negative drills for Iter 102 (2026-05-18): Component 7 sink
// injection (FallbackHandler + ResilientExecutor).
// FallbackHandler: 2 console.warn emissions → ConsoleWarnEventSink.
// ResilientExecutor: 1 console.log (success) + 1 console.error
// (failure) → StreamRoutedEventSink.

import { describe, it, expect, vi } from "vitest";
import { FallbackHandler } from "./fallback-handler";
import { ResilientExecutor } from "./resilient-executor";
import { CircuitBreaker } from "./circuit-breaker";
import {
  EventSink,
  EventRecord,
  InMemoryEventSink,
} from "../06-observability/sinks";
import { ResilienceContext, ResiliencePolicy } from "./types";

const POLICY: ResiliencePolicy = {
  timeoutMs: 100, maxRetries: 0, retryDelayMs: 1,
  failureThreshold: 3, resetAfterMs: 50,
};

const CTX: ResilienceContext = {
  requestId: "r-1", component: "test", traceId: "tr",
};

describe("Iter 102 — FallbackHandler sink injection (P1)", () => {
  it("BACKDOOR: default routes fallback_triggered → console.warn", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      await new FallbackHandler().executeFallback(CTX, async () => "x");
      const events = warn.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "fallback_triggered");
      expect(events.length).toBe(1);
    } finally {
      warn.mockRestore();
    }
  });

  it("BACKDOOR: default routes fallback_unavailable → console.warn (no-fallback case)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      try {
        await new FallbackHandler().executeFallback(CTX);
      } catch { /* expected */ }
      const events = warn.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "fallback_unavailable");
      expect(events.length).toBe(1);
    } finally {
      warn.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures both event types; console.warn silent", async () => {
    const sink = new InMemoryEventSink();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const h = new FallbackHandler(sink);
      await h.executeFallback(CTX, async () => "x");
      try { await h.executeFallback(CTX); } catch { /* expected */ }

      expect(sink.size()).toBe(2);
      expect(sink.list()[0].type).toBe("fallback_triggered");
      expect(sink.list()[1].type).toBe("fallback_unavailable");
      expect(warn.mock.calls.length).toBe(0);
    } finally {
      warn.mockRestore();
    }
  });

  it("fallback_triggered carries fallbackSource tag (iter 13 regression)", async () => {
    const sink = new InMemoryEventSink();
    await new FallbackHandler(sink).executeFallback(CTX, async () => ({
      data: "cached", source: "cache" as const,
    }));
    expect(sink.list()[0].fallbackSource).toBe("cache");
  });
});

describe("Iter 102 — ResilientExecutor sink injection (P1)", () => {
  it("BACKDOOR: default routes resilience_success → console.log", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const cb = new CircuitBreaker(POLICY);
      const exec = new ResilientExecutor(cb, POLICY);
      await exec.execute(CTX, async () => "ok");
      const evts = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "resilience_success");
      expect(evts.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: default routes resilience_failure → console.error", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const cb = new CircuitBreaker(POLICY);
      const exec = new ResilientExecutor(cb, POLICY);
      await exec.execute(CTX, async () => { throw new Error("boom"); });
      const evts = err.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "resilience_failure");
      expect(evts.length).toBe(1);
    } finally {
      err.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures BOTH streams; consoles silent", async () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const cb = new CircuitBreaker(POLICY);
      const exec = new ResilientExecutor(cb, POLICY, { sink });
      await exec.execute(CTX, async () => "ok");
      await exec.execute(CTX, async () => { throw new Error("boom"); });

      const types = sink.list().map((r) => r.type).sort();
      expect(types).toEqual(["resilience_failure", "resilience_success"]);
      // Filter to lifecycle events; ignore unrelated console output.
      expect(log.mock.calls.filter((c) => {
        try { return JSON.parse(c[0] as string).type === "resilience_success"; }
        catch { return false; }
      }).length).toBe(0);
      expect(err.mock.calls.filter((c) => {
        try { return JSON.parse(c[0] as string).type === "resilience_failure"; }
        catch { return false; }
      }).length).toBe(0);
    } finally {
      log.mockRestore();
      err.mockRestore();
    }
  });

  it("custom sink routes BOTH ResilientExecutor and FallbackHandler emissions", async () => {
    const captured: EventRecord[] = [];
    class UnifiedSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const sink = new UnifiedSink();
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY, {
      sink,
      fallbackHandler: new FallbackHandler(sink),
    });
    await exec.execute<string>(
      CTX,
      async () => { throw new Error("boom"); },
      async () => "fallback",
    );
    const types = captured.map((r) => r.type);
    expect(types).toContain("resilience_failure");
    expect(types).toContain("fallback_triggered");
  });

  it("StreamRoutedEventSink strips _stream from console payloads", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const cb = new CircuitBreaker(POLICY);
      const exec = new ResilientExecutor(cb, POLICY);
      await exec.execute(CTX, async () => "ok");
      const payload = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .find((p) => p.type === "resilience_success");
      expect(payload._stream).toBeUndefined();
    } finally {
      log.mockRestore();
    }
  });

  it("custom sink sees _stream hint on resilience_success (log)", async () => {
    const sink = new InMemoryEventSink();
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY, { sink });
    await exec.execute(CTX, async () => "ok");
    expect(sink.list()[0]._stream).toBe("log");
  });

  it("custom sink sees _stream hint on resilience_failure (error)", async () => {
    const sink = new InMemoryEventSink();
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY, { sink });
    await exec.execute(CTX, async () => { throw new Error("boom"); });
    const fail = sink.list().find((r) => r.type === "resilience_failure");
    expect(fail!._stream).toBe("error");
  });
});
