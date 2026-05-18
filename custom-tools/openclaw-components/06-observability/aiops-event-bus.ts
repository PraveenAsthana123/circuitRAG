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
//         that share that request_id — the on-call's first
//         debug query.
//       - On a "critical" event, auto-emits an incident_correlated
//         entry containing the timeline so downstream systems
//         can route the whole story, not just the last event.
//
//     Real production should ship correlation to an AIOps platform
//     (Datadog Incident Mgmt, PagerDuty AIOps). This stub closes
//     the "events scattered, no timeline" gap.

import { AIOpsEvent } from "./types";
import { EventSink, ConsoleEventSink } from "./sinks";

const DEFAULT_RETAIN_PER_REQUEST = 50;
const DEFAULT_MAX_REQUESTS = 1_000;

export class AIOpsEventBus {
  private readonly buffers = new Map<string, AIOpsEvent[]>();
  private readonly sink: EventSink;

  constructor(
    private readonly retainPerRequest: number = DEFAULT_RETAIN_PER_REQUEST,
    private readonly maxRequests: number = DEFAULT_MAX_REQUESTS,
    // Iter M2.3 (2026-05-18): pluggable sink. Default ConsoleEventSink
    // preserves backcompat; a future KafkaEventSink / WebhookEventSink
    // plugs in unchanged. The bus emits TWO event types via the same
    // sink: "aiops_event" per publish, "aiops_incident_correlated"
    // when severity === "critical" auto-correlates a timeline.
    sink?: EventSink,
  ) {
    if (retainPerRequest < 1) throw new Error("retainPerRequest must be >= 1");
    if (maxRequests < 1) throw new Error("maxRequests must be >= 1");
    this.sink = sink ?? new ConsoleEventSink();
  }

  publish(event: AIOpsEvent): void {
    this.sink.emit({ type: "aiops_event", ...event });

    const reqId = event.context.requestId;
    if (!reqId) return;

    const buf = this.buffers.get(reqId) ?? [];
    buf.push(event);
    if (buf.length > this.retainPerRequest) {
      buf.shift();  // FIFO; keep most recent
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
      this.sink.emit({
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
}
