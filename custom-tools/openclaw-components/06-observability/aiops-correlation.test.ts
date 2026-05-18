// Negative drills for Iter 54 (2026-05-17): AIOpsEventBus correlation.

import { describe, it, expect, vi } from "vitest";
import { AIOpsEventBus } from "./aiops-event-bus";
import { AIOpsEvent, ObservabilityContext } from "./types";

function newEvent(
  reqId: string,
  severity: AIOpsEvent["severity"],
  category: AIOpsEvent["category"] = "runtime",
  message = "test",
): AIOpsEvent {
  const ctx: ObservabilityContext = {
    requestId: reqId, sessionId: "s", userId: "u",
    tenantId: "t", traceId: "tr", component: "x",
  };
  return {
    eventId: `${reqId}-${Date.now()}-${Math.random()}`,
    severity, category, message,
    context: ctx,
    timestamp: new Date().toISOString(),
  };
}

describe("AIOpsEventBus — correlation (P1)", () => {
  it("BACKDOOR CHECK: timeline(reqId) returns events in order", () => {
    const bus = new AIOpsEventBus();
    bus.publish(newEvent("req-1", "info", "runtime", "started"));
    bus.publish(newEvent("req-1", "warning", "latency", "slow"));
    bus.publish(newEvent("req-1", "error", "runtime", "failed"));
    bus.publish(newEvent("req-2", "info", "runtime", "unrelated"));

    const t = bus.timeline("req-1");
    expect(t.length).toBe(3);
    expect(t[0].message).toBe("started");
    expect(t[1].message).toBe("slow");
    expect(t[2].message).toBe("failed");
  });

  it("BACKDOOR CHECK: critical event auto-emits a correlated incident", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const bus = new AIOpsEventBus();
    bus.publish(newEvent("req-1", "info", "runtime", "started"));
    bus.publish(newEvent("req-1", "warning", "latency", "slow"));
    bus.publish(newEvent("req-1", "critical", "runtime", "the bad thing"));

    const correlated = log.mock.calls
      .map((c) => JSON.parse(c[0] as string))
      .find((p) => p.type === "aiops_incident_correlated");
    expect(correlated).toBeDefined();
    expect(correlated.requestId).toBe("req-1");
    expect(correlated.timelineLength).toBe(3);
    expect(correlated.timeline[0].message).toBe("started");
    expect(correlated.timeline[2].message).toBe("the bad thing");
    log.mockRestore();
  });

  it("non-critical events do NOT auto-emit a correlated incident", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const bus = new AIOpsEventBus();
    bus.publish(newEvent("req-1", "warning"));
    bus.publish(newEvent("req-1", "error"));  // 'error' is not 'critical'
    const correlated = log.mock.calls
      .map((c) => JSON.parse(c[0] as string))
      .filter((p) => p.type === "aiops_incident_correlated");
    expect(correlated.length).toBe(0);
    log.mockRestore();
  });

  it("per-request buffer caps at retainPerRequest (FIFO)", () => {
    const bus = new AIOpsEventBus(3 /* retain */, 100);
    for (let i = 0; i < 10; i++) {
      bus.publish(newEvent("req-1", "info", "runtime", `m${i}`));
    }
    const t = bus.timeline("req-1");
    expect(t.length).toBe(3);
    expect(t[0].message).toBe("m7");  // m0..m6 dropped, m7..m9 retained
    expect(t[2].message).toBe("m9");
  });

  it("maxRequests cap evicts oldest tracked request (LRU on insertion)", () => {
    const bus = new AIOpsEventBus(10, 2);
    bus.publish(newEvent("req-A", "info"));
    bus.publish(newEvent("req-B", "info"));
    bus.publish(newEvent("req-C", "info"));
    expect(bus.trackedRequestCount()).toBeLessThanOrEqual(2);
    // req-A (oldest) was evicted.
    expect(bus.timeline("req-A")).toEqual([]);
  });

  it("event without requestId is published but not bufferred", () => {
    const bus = new AIOpsEventBus();
    const ev = newEvent("", "warning");
    ev.context.requestId = "";  // simulate missing
    bus.publish(ev);
    expect(bus.trackedRequestCount()).toBe(0);
  });

  it("constructor rejects sub-1 caps", () => {
    expect(() => new AIOpsEventBus(0, 10)).toThrow();
    expect(() => new AIOpsEventBus(10, 0)).toThrow();
  });
});
