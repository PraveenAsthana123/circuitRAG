// ✅ Iter 22 (2026-05-17): HumanApprovalGate now persists tickets in
//     an ApprovalQueue with TTL + escalation surface. Pre-fix it just
//     console.log'd a "ticket" that no system could later resolve.
//
//     This is still in-memory only — see GAPS Component 10 row
//     "no real queue" for the production fix (Postgres approvals
//     table + UI route).

import { WorkflowContext, WorkflowStep } from "./types";
import { ApprovalQueue } from "./approval-queue";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export class HumanApprovalGate {
  private readonly sink: EventSink;
  // Iter 103 (2026-05-18): pluggable sink for human_approval_required
  // emissions. Default ConsoleEventSink preserves backcompat.
  constructor(
    private readonly queue: ApprovalQueue = new ApprovalQueue(),
    sink?: EventSink,
  ) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  requestApproval(context: WorkflowContext, step: WorkflowStep): string {
    const ticket = this.queue.enqueue({
      workflowId: context.workflowId,
      stepId: step.stepId,
      stepName: step.name,
      tenantId: context.tenantId,
      requestedBy: context.userId,
    });

    this.sink.emit({
      type: "human_approval_required",
      approvalId: ticket.approvalId,
      workflowId: context.workflowId,
      requestId: context.requestId,
      tenantId: context.tenantId,
      stepId: step.stepId,
      stepName: step.name,
      expiresAt: ticket.expiresAt,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    });

    return ticket.approvalId;
  }

  /** Expose the queue for operator tooling + tests. */
  getQueue(): ApprovalQueue {
    return this.queue;
  }
}
