import { describe, expect, it } from "vitest";
import { InMemoryEventSink } from "../06-observability/sinks";
import {
  ApprovalGate,
  HumanReviewQueue,
  HumanReviewStatus,
  HumanReviewTicket,
  InMemoryHumanReviewQueue,
} from "./approval-gate";
import { GuardrailResult } from "./types";

const REVIEW: GuardrailResult = {
  decision: "review",
  findings: [{ ruleId: "INPUT_PII_EMAIL", severity: "medium", message: "email" }],
  explanation: "review",
};

class SpyHumanReviewQueue implements HumanReviewQueue {
  readonly enqueued: HumanReviewTicket[] = [];
  private readonly delegate = new InMemoryHumanReviewQueue();

  enqueue(ticket: HumanReviewTicket): void {
    this.enqueued.push(structuredClone(ticket));
    this.delegate.enqueue(ticket);
  }

  get(ticketId: string): HumanReviewTicket | undefined {
    return this.delegate.get(ticketId);
  }

  list(status?: HumanReviewStatus): HumanReviewTicket[] {
    return this.delegate.list(status);
  }

  resolve(
    ticketId: string,
    status: Exclude<HumanReviewStatus, "pending">,
    by: string,
    reason?: string,
  ): HumanReviewTicket {
    return this.delegate.resolve(ticketId, status, by, reason);
  }
}

describe("ApprovalGate human-review queue seam", () => {
  it("persists created tickets through the injected queue", () => {
    const sink = new InMemoryEventSink();
    const queue = new SpyHumanReviewQueue();
    const gate = new ApprovalGate(sink, queue);

    const ticketId = gate.createApprovalTicket(REVIEW);

    expect(queue.enqueued).toHaveLength(1);
    expect(queue.enqueued[0]).toMatchObject({
      ticketId,
      decision: "review",
      status: "pending",
      findings: REVIEW.findings,
    });
    expect(gate.getTicket(ticketId)?.status).toBe("pending");
  });

  it("keeps approval_ticket event schema unchanged while queue stores canonical ticket", () => {
    const sink = new InMemoryEventSink();
    const queue = new SpyHumanReviewQueue();
    const gate = new ApprovalGate(sink, queue);

    const ticketId = gate.createApprovalTicket(REVIEW);
    const event = sink.list()[0];

    expect(Object.keys(event).sort()).toEqual(
      ["decision", "findings", "ticketId", "timestamp", "type"].sort(),
    );
    expect(event.ticketId).toBe(ticketId);
    expect(queue.enqueued[0].createdAt).toBe(event.timestamp);
  });

  it("supports approve and deny transitions for future human-review UI", () => {
    const gate = new ApprovalGate(new InMemoryEventSink());
    const approveId = gate.createApprovalTicket(REVIEW);
    const denyId = gate.createApprovalTicket(REVIEW);

    expect(gate.approveTicket(approveId, "operator-1", "safe")).toMatchObject({
      status: "approved",
      resolvedBy: "operator-1",
      reason: "safe",
    });
    expect(gate.denyTicket(denyId, "operator-2", "unsafe")).toMatchObject({
      status: "denied",
      resolvedBy: "operator-2",
      reason: "unsafe",
    });
    expect(gate.listTickets("pending")).toHaveLength(0);
  });

  it("default in-memory queue keeps defensive copies", () => {
    const gate = new ApprovalGate(new InMemoryEventSink());
    const result: GuardrailResult = structuredClone(REVIEW);
    const ticketId = gate.createApprovalTicket(result);

    result.findings[0].message = "mutated-after-create";
    const read = gate.getTicket(ticketId)!;
    read.findings[0].message = "mutated-after-read";

    expect(gate.getTicket(ticketId)?.findings[0].message).toBe("email");
  });
});
