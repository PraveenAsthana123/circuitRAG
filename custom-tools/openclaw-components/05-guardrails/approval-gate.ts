import { randomUUID } from "crypto";
import { GuardrailResult } from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export class ApprovalGate {
  private readonly sink: EventSink;
  // Iter 97 (2026-05-18): pluggable sink for approval_ticket
  // emissions. Default ConsoleEventSink preserves backcompat;
  // a future SQS / Kafka / PagerDuty sink plugs in unchanged.
  // Reuses EventSink (M2.3) — opaque event-shaped JSON.
  constructor(sink?: EventSink) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  requiresHumanApproval(result: GuardrailResult): boolean {
    return result.decision === "review";
  }

  createApprovalTicket(result: GuardrailResult): string {
    const ticketId = randomUUID();

    this.sink.emit({
      type: "approval_ticket",
      ticketId,
      decision: result.decision,
      findings: result.findings,
      timestamp: new Date().toISOString(),
    });

    return ticketId;
  }
}
