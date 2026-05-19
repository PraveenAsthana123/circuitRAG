// Negative drills for Iter 98 (2026-05-18): Gateway error sink
// injection. Pre-fix: gateway error emissions went straight to
// console.error, blocking the path to Sentry / Datadog Errors /
// PagerDuty integration. Now: pluggable EventSink, default
// ConsoleErrorEventSink (preserves console.error stream routing
// that iter 71's request-id-baggage drill depends on).

import { describe, it, expect, vi } from "vitest";
import { Gateway } from "./gateway";
import { SessionManager } from "./session-manager";
import { RateLimiter } from "./rate-limiter";
import { NoOpAuthMiddleware } from "./auth";
import { UserMessage } from "./types";
import {
  EventSink,
  EventRecord,
  InMemoryEventSink,
  ConsoleErrorEventSink,
} from "../06-observability/sinks";

function newGateway(errorSink?: EventSink): Gateway {
  return new Gateway(
    new SessionManager(),
    new RateLimiter(),
    new NoOpAuthMiddleware(true),
    1024,
    errorSink,
  );
}

const VALID_MSG: UserMessage = {
  messageId: "m-1", userId: "u-1", channel: "web",
  text: "hello", timestamp: new Date().toISOString(),
  tenantId: "t-1",
};

const OVERSIZED_MSG: UserMessage = {
  ...VALID_MSG,
  text: "x".repeat(2000),  // > 1024 byte cap → PAYLOAD_TOO_LARGE
};

describe("Iter 98 — Gateway error sink injection (P1)", () => {
  it("BACKDOOR: default sink emits to console.error (backcompat — iter 71 spy contract)", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const gw = newGateway();
      await gw.handleMessage(OVERSIZED_MSG);
      const errLogs = err.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "gateway_error");
      expect(errLogs.length).toBe(1);
      expect(errLogs[0].errorCode).toBe("PAYLOAD_TOO_LARGE");
    } finally {
      err.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures; console.error silent", async () => {
    const sink = new InMemoryEventSink();
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const gw = newGateway(sink);
      await gw.handleMessage(OVERSIZED_MSG);
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("gateway_error");
      expect(sink.list()[0].errorCode).toBe("PAYLOAD_TOO_LARGE");
      // Nothing landed on console.error.
      const errLogs = err.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "gateway_error");
      expect(errLogs.length).toBe(0);
    } finally {
      err.mockRestore();
    }
  });

  it("BACKDOOR: successful request does NOT emit gateway_error (regression)", async () => {
    const sink = new InMemoryEventSink();
    const gw = newGateway(sink);
    const result = await gw.handleMessage(VALID_MSG);
    expect(result.ok).toBe(true);
    const errors = sink.list().filter((r) => r.type === "gateway_error");
    expect(errors.length).toBe(0);
  });

  it("BACKDOOR: each error emission has unique requestId (no recycling)", async () => {
    const sink = new InMemoryEventSink();
    const gw = newGateway(sink);
    await gw.handleMessage(OVERSIZED_MSG);
    await gw.handleMessage(OVERSIZED_MSG);
    expect(sink.size()).toBe(2);
    expect(sink.list()[0].requestId).not.toBe(sink.list()[1].requestId);
  });

  it("gateway_error payload canonical 5-field set (schema fingerprint)", async () => {
    const sink = new InMemoryEventSink();
    await newGateway(sink).handleMessage(OVERSIZED_MSG);
    const r = sink.list()[0];
    const keys = Object.keys(r).sort();
    expect(keys).toEqual(
      ["detail", "errorCode", "requestId", "timestamp", "type"].sort(),
    );
  });

  it("BACKDOOR: error response envelope's requestId MATCHES the sink emission (audit correlation)", async () => {
    const sink = new InMemoryEventSink();
    const result = await newGateway(sink).handleMessage(OVERSIZED_MSG);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(sink.list()[0].requestId).toBe(result.error.requestId);
    }
  });

  it("custom sink routes to Sentry-like consumer (extension point)", async () => {
    const captured: EventRecord[] = [];
    class SentrySink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    await newGateway(new SentrySink()).handleMessage(OVERSIZED_MSG);
    expect(captured.length).toBe(1);
    expect(captured[0].type).toBe("gateway_error");
  });

  it("ConsoleErrorEventSink routes to console.error (not console.log)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      new ConsoleErrorEventSink().emit({ type: "test", x: 1 });
      expect(err.mock.calls.length).toBe(1);
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
      err.mockRestore();
    }
  });

  it("ConsoleErrorEventSink emits single-line JSON (log-shipper safety)", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      new ConsoleErrorEventSink().emit({ type: "test" });
      expect((err.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      err.mockRestore();
    }
  });

  it("internal error (non-GatewayError throw) still flows through sink", async () => {
    // Construct a Gateway with a SessionManager that throws unexpectedly.
    const sink = new InMemoryEventSink();
    const brokenSessionManager = {
      getOrCreateSession: () => { throw new Error("disk full"); },
    } as unknown as SessionManager;
    const gw = new Gateway(
      brokenSessionManager,
      new RateLimiter(),
      new NoOpAuthMiddleware(true),
      1024,
      sink,
    );
    const result = await gw.handleMessage(VALID_MSG);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.errorCode).toBe("INTERNAL");
    }
    expect(sink.size()).toBe(1);
    expect(sink.list()[0].errorCode).toBe("INTERNAL");
  });
});
