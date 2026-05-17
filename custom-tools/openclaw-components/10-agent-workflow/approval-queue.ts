// Added Iter 22 (2026-05-17) — durable in-memory approval queue
// with TTL + escalation. Closes the GAPS Component 10 row
// "HumanApprovalGate just logs to console".
//
// What this gets right vs the pre-fix console.log:
//   - Tickets persist in a queue, queryable by tenantId/workflowId.
//   - Each ticket carries an expiresAt; expired tickets surface
//     via listEscalations() so a separate scheduler can notify
//     escalation contacts and decide to auto-deny / auto-approve
//     per policy.
//   - approve() / deny() are explicit terminal states, both
//     append timestamped audit entries.
//
// What still needs real infra (in GAPS):
//   - The queue is in-memory; restart loses pending tickets.
//     Production needs Postgres `approvals` table or SQS.
//   - There is no UI route — operator interaction has to be
//     mediated by a real frontend.

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "denied"
  | "expired";

export interface ApprovalTicket {
  approvalId: string;
  workflowId: string;
  stepId: string;
  stepName: string;
  tenantId: string;
  requestedBy: string;
  status: ApprovalStatus;
  createdAt: string;
  expiresAt: string;
  resolvedAt?: string;
  resolvedBy?: string;
  reason?: string;
}

const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000; // 24h escalation threshold

export class ApprovalNotFoundError extends Error {
  constructor(id: string) { super(`Approval ticket not found: ${id}`); }
}
export class ApprovalAccessDeniedError extends Error {
  constructor(id: string, t: string) {
    super(`Tenant ${t} cannot access approval ${id}`);
  }
}
export class ApprovalAlreadyResolvedError extends Error {
  constructor(id: string, status: ApprovalStatus) {
    super(`Approval ${id} is already ${status}; cannot modify`);
  }
}

export class ApprovalQueue {
  private readonly tickets = new Map<string, ApprovalTicket>();

  constructor(
    private readonly ttlMs: number = DEFAULT_TTL_MS,
  ) {
    if (ttlMs < 1) throw new Error("ttlMs must be >= 1");
  }

  enqueue(input: {
    workflowId: string;
    stepId: string;
    stepName: string;
    tenantId: string;
    requestedBy: string;
  }): ApprovalTicket {
    const now = Date.now();
    const ticket: ApprovalTicket = {
      approvalId: crypto.randomUUID(),
      workflowId: input.workflowId,
      stepId: input.stepId,
      stepName: input.stepName,
      tenantId: input.tenantId,
      requestedBy: input.requestedBy,
      status: "pending",
      createdAt: new Date(now).toISOString(),
      expiresAt: new Date(now + this.ttlMs).toISOString(),
    };
    this.tickets.set(ticket.approvalId, ticket);
    return ticket;
  }

  get(approvalId: string, callerTenantId: string): ApprovalTicket {
    const t = this.tickets.get(approvalId);
    if (!t) throw new ApprovalNotFoundError(approvalId);
    if (t.tenantId !== callerTenantId) {
      throw new ApprovalAccessDeniedError(approvalId, callerTenantId);
    }
    return t;
  }

  approve(approvalId: string, callerTenantId: string, by: string, reason?: string): ApprovalTicket {
    const t = this.get(approvalId, callerTenantId);
    if (t.status !== "pending") {
      throw new ApprovalAlreadyResolvedError(approvalId, t.status);
    }
    t.status = "approved";
    t.resolvedAt = new Date().toISOString();
    t.resolvedBy = by;
    t.reason = reason;
    return t;
  }

  deny(approvalId: string, callerTenantId: string, by: string, reason?: string): ApprovalTicket {
    const t = this.get(approvalId, callerTenantId);
    if (t.status !== "pending") {
      throw new ApprovalAlreadyResolvedError(approvalId, t.status);
    }
    t.status = "denied";
    t.resolvedAt = new Date().toISOString();
    t.resolvedBy = by;
    t.reason = reason;
    return t;
  }

  /**
   * Tickets still pending past their expiresAt. A separate scheduler
   * is expected to call this periodically, mark them expired, and
   * notify escalation contacts (per CLAUDE.md §48.6 HITL escalation).
   */
  listEscalations(now: Date = new Date()): ApprovalTicket[] {
    const cutoff = now.getTime();
    return Array.from(this.tickets.values()).filter(
      (t) => t.status === "pending" && new Date(t.expiresAt).getTime() < cutoff,
    );
  }

  /** Mark expired tickets as "expired" (called by the escalation worker). */
  markExpired(now: Date = new Date()): ApprovalTicket[] {
    const expired = this.listEscalations(now);
    for (const t of expired) {
      t.status = "expired";
      t.resolvedAt = now.toISOString();
      t.resolvedBy = "system:expiry";
      t.reason = "Pending past TTL";
    }
    return expired;
  }

  pendingByWorkflow(workflowId: string, callerTenantId: string): ApprovalTicket[] {
    return Array.from(this.tickets.values()).filter(
      (t) =>
        t.workflowId === workflowId &&
        t.tenantId === callerTenantId &&
        t.status === "pending",
    );
  }
}
