// Negative drills for M2.3 (2026-05-18): AIOpsEventBus sink injection.
// Mirrors M2.1+M2.2. AIOpsEventBus emits TWO event types: aiops_event
// per publish + aiops_incident_correlated on critical severity.
// Both flow through the same sink so a future KafkaEventSink /
// WebhookEventSink plugs in unchanged.

import { describe, it, expect, vi } from "vitest";
import { AIOpsEventBus } from "./aiops-event-bus";
import {
  ConsoleEventSink,
  InMemoryEventSink,
  EventSink,
  EventRecord,
} from "./sinks";
import { AIOpsEvent } from "./types";

function makeEvent(
  requestId: string,
  severity: AIOpsEvent["severity"] = "info",
  message = "test",
): AIOpsEvent {
  return {
    eventId: `e-${Math.random().toString(36).slice(2)}`,
    severity,
    category: "runtime",
    message,
    timestamp: new Date().toISOString(),
    context: {
      requestId,
      sessionId: "s",
      userId: "u",
      tenantId: "t",
      traceId: "tr",
      component: "test",
    },
  };
}

describe("M2.3 — AIOpsEventBus sink injection (P1)", () => {
  it("BACKDOOR: default sink emits to console (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new AIOpsEventBus().publish(makeEvent("r-1"));
      expect(log.mock.calls.length).toBe(1);
      const p = JSON.parse(log.mock.calls[0][0] as string);
      expect(p.type).toBe("aiops_event");
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures; console silent", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const bus = new AIOpsEventBus(50, 1000, sink);
      bus.publish(makeEvent("r-1", "info"));
      bus.publish(makeEvent("r-1", "warning"));

      expect(sink.size()).toBe(2);
      expect(sink.list()[0].type).toBe("aiops_event");
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: critical event emits aiops_event + aiops_incident_correlated (regression iter 54)", () => {
    const sink = new InMemoryEventSink();
    const bus = new AIOpsEventBus(50, 1000, sink);
    bus.publish(makeEvent("r-1", "info", "started"));
    bus.publish(makeEvent("r-1", "warning", "slow"));
    bus.publish(makeEvent("r-1", "critical", "the bad thing"));

    // 3 "aiops_event" entries + 1 "aiops_incident_correlated"
    const events = sink.list().filter((r) => r.type === "aiops_event");
    const correlations = sink.list().filter((r) => r.type === "aiops_incident_correlated");
    expect(events.length).toBe(3);
    expect(correlations.length).toBe(1);

    const corr = correlations[0];
    expect(corr.requestId).toBe("r-1");
    expect(corr.timelineLength).toBe(3);
    expect(Array.isArray(corr.timeline)).toBe(true);
  });

  it("BACKDOOR: non-critical events do NOT auto-emit incident_correlated", () => {
    const sink = new InMemoryEventSink();
    const bus = new AIOpsEventBus(50, 1000, sink);
    bus.publish(makeEvent("r-1", "info"));
    bus.publish(makeEvent("r-1", "warning"));
    bus.publish(makeEvent("r-1", "error"));  // 'error' is not 'critical'
    const correlations = sink.list().filter((r) => r.type === "aiops_incident_correlated");
    expect(correlations.length).toBe(0);
  });

  it("BACKDOOR: per-request buffer caps at retainPerRequest (regression)", () => {
    const sink = new InMemoryEventSink();
    const bus = new AIOpsEventBus(3, 100, sink);
    for (let i = 0; i < 10; i++) {
      bus.publish(makeEvent("r-1", "info", `m${i}`));
    }
    expect(bus.timeline("r-1").length).toBe(3);
    // Sink still got all 10 emissions (only the timeline buffer is capped).
    expect(sink.list().filter((r) => r.type === "aiops_event").length).toBe(10);
  });

  it("InMemoryEventSink.list returns defensive copies", () => {
    const sink = new InMemoryEventSink();
    new AIOpsEventBus(50, 1000, sink).publish(makeEvent("r-1"));
    const list = sink.list();
    list[0].type = "MUTATED";
    expect(sink.list()[0].type).toBe("aiops_event");
  });

  it("InMemoryEventSink: maxRecords FIFO cap", () => {
    const sink = new InMemoryEventSink(3);
    const bus = new AIOpsEventBus(50, 1000, sink);
    for (let i = 0; i < 10; i++) {
      bus.publish(makeEvent(`r-${i}`));
    }
    expect(sink.size()).toBe(3);
  });

  it("custom sink routes both event types (extension point)", () => {
    const captured: EventRecord[] = [];
    class RoutingSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const bus = new AIOpsEventBus(50, 1000, new RoutingSink());
    bus.publish(makeEvent("r-1", "critical", "bad"));
    expect(captured.length).toBe(2);
    expect(captured[0].type).toBe("aiops_event");
    expect(captured[1].type).toBe("aiops_incident_correlated");
  });

  it("ConsoleEventSink emits single-line JSON", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ConsoleEventSink().emit({ type: "x", value: 1 });
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("event WITHOUT requestId still emits to sink (regression — buffer skipped, emit not)", () => {
    const sink = new InMemoryEventSink();
    const bus = new AIOpsEventBus(50, 1000, sink);
    const ev = makeEvent("", "warning");
    ev.context.requestId = "";
    bus.publish(ev);
    expect(sink.size()).toBe(1);
    expect(bus.trackedRequestCount()).toBe(0);
  });
});
