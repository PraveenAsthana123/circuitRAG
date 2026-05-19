import { randomUUID } from "crypto";
import { GuardrailDecision, GuardrailFinding, GuardrailResult } from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export type HumanReviewStatus = "pending" | "approved" | "denied";

export interface HumanReviewTicket {
  ticketId: string;
  decision: GuardrailDecision;
  findings: GuardrailFinding[];
  status: HumanReviewStatus;
  createdAt: string;
  resolvedAt?: string;
  resolvedBy?: string;
  reason?: string;
}

export interface HumanReviewQueue {
  enqueue(ticket: HumanReviewTicket): void;
  get(ticketId: string): HumanReviewTicket | undefined;
  list(status?: HumanReviewStatus): HumanReviewTicket[];
  resolve(
    ticketId: string,
    status: Exclude<HumanReviewStatus, "pending">,
    by: string,
    reason?: string,
  ): HumanReviewTicket;
}

export class HumanReviewTicketNotFoundError extends Error {
  constructor(ticketId: string) {
    super(`Human review ticket not found: ${ticketId}`);
    this.name = "HumanReviewTicketNotFoundError";
  }
}

export class HumanReviewTicketAlreadyResolvedError extends Error {
  constructor(ticketId: string, status: HumanReviewStatus) {
    super(`Human review ticket ${ticketId} is already ${status}`);
    this.name = "HumanReviewTicketAlreadyResolvedError";
  }
}

export class InMemoryHumanReviewQueue implements HumanReviewQueue {
  private readonly tickets = new Map<string, HumanReviewTicket>();

  enqueue(ticket: HumanReviewTicket): void {
    this.tickets.set(ticket.ticketId, structuredClone(ticket));
  }

  get(ticketId: string): HumanReviewTicket | undefined {
    const ticket = this.tickets.get(ticketId);
    return ticket ? structuredClone(ticket) : undefined;
  }

  list(status?: HumanReviewStatus): HumanReviewTicket[] {
    return Array.from(this.tickets.values())
      .filter((ticket) => status === undefined || ticket.status === status)
      .map((ticket) => structuredClone(ticket));
  }

  resolve(
    ticketId: string,
    status: Exclude<HumanReviewStatus, "pending">,
    by: string,
    reason?: string,
  ): HumanReviewTicket {
    const ticket = this.tickets.get(ticketId);
    if (!ticket) throw new HumanReviewTicketNotFoundError(ticketId);
    if (ticket.status !== "pending") {
      throw new HumanReviewTicketAlreadyResolvedError(ticketId, ticket.status);
    }
    ticket.status = status;
    ticket.resolvedAt = new Date().toISOString();
    ticket.resolvedBy = by;
    ticket.reason = reason;
    return structuredClone(ticket);
  }
}

export class ApprovalGate {
  private readonly sink: EventSink;
  private readonly queue: HumanReviewQueue;

  // Iter 103 (2026-05-19): pluggable human-review queue. The
  // approval_ticket event remains the notification/export path; the
  // queue is the canonical local ticket store for future SQS/Kafka/UI.
  constructor(sink?: EventSink, queue?: HumanReviewQueue) {
    this.sink = sink ?? new ConsoleEventSink();
    this.queue = queue ?? new InMemoryHumanReviewQueue();
  }

  requiresHumanApproval(result: GuardrailResult): boolean {
    return result.decision === "review";
  }

  createApprovalTicket(result: GuardrailResult): string {
    const ticketId = randomUUID();
    const timestamp = new Date().toISOString();

    this.queue.enqueue({
      ticketId,
      decision: result.decision,
      findings: structuredClone(result.findings),
      status: "pending",
      createdAt: timestamp,
    });

    this.sink.emit({
      type: "approval_ticket",
      ticketId,
      decision: result.decision,
      findings: result.findings,
      timestamp,
    });

    return ticketId;
  }

  getTicket(ticketId: string): HumanReviewTicket | undefined {
    return this.queue.get(ticketId);
  }

  listTickets(status?: HumanReviewStatus): HumanReviewTicket[] {
    return this.queue.list(status);
  }

  approveTicket(ticketId: string, by: string, reason?: string): HumanReviewTicket {
    return this.queue.resolve(ticketId, "approved", by, reason);
  }

  denyTicket(ticketId: string, by: string, reason?: string): HumanReviewTicket {
    return this.queue.resolve(ticketId, "denied", by, reason);
  }
}
