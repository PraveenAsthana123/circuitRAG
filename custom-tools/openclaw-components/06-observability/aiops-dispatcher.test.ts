import { describe, it, expect } from "vitest";
import { AIOpsEventBus } from "./aiops-event-bus";
import {
  InMemoryAIOpsEventDispatcher,
  KafkaAIOpsEventDispatcher,
  WebhookAIOpsEventDispatcher,
} from "./aiops-dispatcher";
import { AIOpsEvent } from "./types";

function makeEvent(
  requestId: string,
  severity: AIOpsEvent["severity"] = "info",
): AIOpsEvent {
  return {
    eventId: `event-${requestId}-${severity}`,
    severity,
    category: "runtime",
    message: `${severity} message`,
    timestamp: "2026-05-19T00:00:00.000Z",
    context: {
      requestId,
      sessionId: "s",
      userId: "u",
      tenantId: "tenant-A",
      traceId: "trace-A",
      component: "planner",
    },
  };
}

describe("Iter 106 - AIOps event bus dispatcher boundary", () => {
  it("dispatches aiops events as topic/key envelopes", () => {
    const dispatcher = new InMemoryAIOpsEventDispatcher();
    const bus = new AIOpsEventBus(50, 1000, undefined, dispatcher);

    bus.publish(makeEvent("req-1", "warning"));

    expect(dispatcher.size()).toBe(1);
    const envelope = dispatcher.list()[0];
    expect(envelope.topic).toBe("aiops.events");
    expect(envelope.key).toBe("req-1");
    expect(envelope.record.type).toBe("aiops_event");
    expect(envelope.record.eventId).toBe("event-req-1-warning");
  });

  it("dispatches critical correlations to the incident topic", () => {
    const dispatcher = new InMemoryAIOpsEventDispatcher();
    const bus = new AIOpsEventBus(50, 1000, undefined, dispatcher);

    bus.publish(makeEvent("req-1", "info"));
    bus.publish(makeEvent("req-1", "critical"));

    const envelopes = dispatcher.list();
    expect(envelopes.map((e) => e.topic)).toEqual([
      "aiops.events",
      "aiops.events",
      "aiops.incidents",
    ]);
    const incident = envelopes[2];
    expect(incident.key).toBe("req-1");
    expect(incident.record.type).toBe("aiops_incident_correlated");
    expect(incident.record.timelineLength).toBe(2);
  });

  it("in-memory dispatcher is bounded and returns defensive copies", () => {
    const dispatcher = new InMemoryAIOpsEventDispatcher(2);
    const bus = new AIOpsEventBus(50, 1000, undefined, dispatcher);

    bus.publish(makeEvent("req-1"));
    bus.publish(makeEvent("req-2"));
    bus.publish(makeEvent("req-3"));

    expect(dispatcher.size()).toBe(2);
    expect(dispatcher.list().map((e) => e.key)).toEqual(["req-2", "req-3"]);
    const copy = dispatcher.list();
    copy[0].record.type = "mutated";
    expect(dispatcher.list()[0].record.type).toBe("aiops_event");
  });

  it("Kafka dispatcher maps envelopes to topic/key/value producer calls", () => {
    const sent: Array<{ topic: string; messages: Array<{ key: string; value: string }> }> = [];
    const dispatcher = new KafkaAIOpsEventDispatcher({
      send(input) {
        sent.push(input);
      },
    });
    const bus = new AIOpsEventBus(50, 1000, undefined, dispatcher);

    bus.publish(makeEvent("req-kafka"));

    expect(sent.length).toBe(1);
    expect(sent[0].topic).toBe("aiops.events");
    expect(sent[0].messages[0].key).toBe("req-kafka");
    expect(JSON.parse(sent[0].messages[0].value).type).toBe("aiops_event");
  });

  it("Webhook dispatcher maps envelopes to topic/key/payload posts", () => {
    const posts: Array<{ topic: string; key: string; payload: Record<string, unknown> }> = [];
    const dispatcher = new WebhookAIOpsEventDispatcher({
      post(input) {
        posts.push(input);
      },
    });
    const bus = new AIOpsEventBus(50, 1000, undefined, dispatcher);

    bus.publish(makeEvent("req-webhook", "error"));

    expect(posts.length).toBe(1);
    expect(posts[0].topic).toBe("aiops.events");
    expect(posts[0].key).toBe("req-webhook");
    expect(posts[0].payload.type).toBe("aiops_event");
    expect(posts[0].payload.severity).toBe("error");
  });
});
