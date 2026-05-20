// ✅ P1 IMPROVED (Iter 54, 2026-05-17): event correlation by
//     request_id with per-request incident timeline assembly.
//     Pre-fix: events were emitted independently to console.log;
//     debugging an incident required grepping for a request_id
//     and manually ordering events.
//
//     Now:
//       - publish() retains a per-request_id buffer of recent
//         events (in-memory, cap-bounded).
//       - timeline(requestId) returns the ordered list of events
//         that share the request_id — the on-call's first
//         debug query.
//       - On a "critical" event, auto-emits an incident_correlated
//         entry containing the timeline so downstream systems
//         can route the whole story, not just the last event.
//
// ✅ P0 IMPROVED (Iter 106, 2026-05-19): event-bus dispatcher
//     boundary. AIOps events are now dispatched as topic/key
//     envelopes; Kafka/webhook/outbox implementations plug into
//     AIOpsEventDispatcher while the default sink dispatcher
//     preserves console JSON backcompat.

import { AIOpsEvent } from "./types";
import { EventSink, ConsoleEventSink, EventRecord } from "./sinks";
import {
  AIOpsDispatchEnvelope,
  AIOpsEventDispatcher,
  AIOpsTopic,
  SinkAIOpsEventDispatcher,
} from "./aiops-dispatcher";

const DEFAULT_RETAIN_PER_REQUEST = 50;
const DEFAULT_MAX_REQUESTS = 1_000;

export class AIOpsEventBus {
  private readonly buffers = new Map<string, AIOpsEvent[]>();
  private readonly dispatcher: AIOpsEventDispatcher;

  constructor(
    private readonly retainPerRequest: number = DEFAULT_RETAIN_PER_REQUEST,
    private readonly maxRequests: number = DEFAULT_MAX_REQUESTS,
    // Iter M2.3 (2026-05-18): pluggable sink. Default ConsoleEventSink
    // preserves backcompat. Iter 106 adds dispatcher envelopes on top:
    // callers can keep using sink injection, or pass a dispatcher for
    // Kafka/webhook/outbox style delivery.
    sink?: EventSink,
    dispatcher?: AIOpsEventDispatcher,
  ) {
    if (retainPerRequest < 1) throw new Error("retainPerRequest must be >= 1");
    if (maxRequests < 1) throw new Error("maxRequests must be >= 1");
    this.dispatcher = dispatcher ?? new SinkAIOpsEventDispatcher(sink ?? new ConsoleEventSink());
  }

  publish(event: AIOpsEvent): void {
    this.dispatch("aiops.events", event.context.requestId || event.eventId, {
      type: "aiops_event",
      ...event,
    });

    const reqId = event.context.requestId;
    if (!reqId) return;

    const buf = this.buffers.get(reqId) ?? [];
    buf.push(event);
    if (buf.length > this.retainPerRequest) {
      buf.shift();
    }
    this.buffers.set(reqId, buf);

    // Cap total tracked requests — LRU on insertion order.
    if (this.buffers.size > this.maxRequests) {
      const oldest = this.buffers.keys().next().value;
      if (oldest !== undefined) this.buffers.delete(oldest);
    }

    // Auto-emit correlated incident on critical events.
    if (event.severity === "critical") {
      const timeline = this.timeline(reqId);
      this.dispatch("aiops.incidents", reqId, {
        type: "aiops_incident_correlated",
        requestId: reqId,
        tenantId: event.context.tenantId,
        triggerEventId: event.eventId,
        timelineLength: timeline.length,
        timeline: timeline.map((e) => ({
          eventId: e.eventId,
          severity: e.severity,
          category: e.category,
          message: e.message,
          timestamp: e.timestamp,
        })),
      });
    }
  }

  /** Ordered events for a given request_id. Empty if unknown. */
  timeline(requestId: string): AIOpsEvent[] {
    return [...(this.buffers.get(requestId) ?? [])];
  }

  /** Test helper. */
  trackedRequestCount(): number {
    return this.buffers.size;
  }

  private dispatch(topic: AIOpsTopic, key: string, record: EventRecord): void {
    const envelope: AIOpsDispatchEnvelope = {
      topic,
      key,
      record,
      timestamp: new Date().toISOString(),
    };
    this.dispatcher.dispatch(envelope);
  }
}
