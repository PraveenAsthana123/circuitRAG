// Negative drills for Iter 88 (2026-05-18): ApprovalQueue edge cases.
// Existing 8 tests cover happy-path enqueue/get/approve/deny/listEscalations/
// pendingByWorkflow. This drill covers: constructor validation,
// markExpired idempotency, double-resolve guard, listEscalations
// excludes resolved, TTL boundary, pendingByWorkflow cross-tenant.

import { describe, it, expect } from "vitest";
import {
  ApprovalQueue,
  ApprovalAlreadyResolvedError,
  ApprovalAccessDeniedError,
} from "./approval-queue";

const INPUT = {
  workflowId: "wf-1", stepId: "s-1", stepName: "exec",
  tenantId: "t-1", requestedBy: "user-1",
};

describe("Iter 88 — ApprovalQueue edges (P2)", () => {
  it("BACKDOOR: constructor rejects sub-1 ttlMs", () => {
    expect(() => new ApprovalQueue(0)).toThrow(/ttlMs/);
    expect(() => new ApprovalQueue(-100)).toThrow(/ttlMs/);
  });

  it("BACKDOOR: double-approve throws AlreadyResolvedError", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue(INPUT);
    q.approve(t.approvalId, "t-1", "admin");
    expect(() => q.approve(t.approvalId, "t-1", "admin"))
      .toThrow(ApprovalAlreadyResolvedError);
  });

  it("BACKDOOR: approve-after-deny throws (race-condition guard)", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue(INPUT);
    q.deny(t.approvalId, "t-1", "admin");
    expect(() => q.approve(t.approvalId, "t-1", "admin"))
      .toThrow(ApprovalAlreadyResolvedError);
  });

  it("BACKDOOR: cross-tenant approve denied even on pending ticket", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue(INPUT);
    expect(() => q.approve(t.approvalId, "tenant-attacker", "x"))
      .toThrow(ApprovalAccessDeniedError);
    // Ticket remains pending — attack didn't poison state.
    const fresh = q.get(t.approvalId, "t-1");
    expect(fresh.status).toBe("pending");
  });

  it("BACKDOOR: cross-tenant deny denied (paired symmetric guard)", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue(INPUT);
    expect(() => q.deny(t.approvalId, "tenant-attacker", "x"))
      .toThrow(ApprovalAccessDeniedError);
  });

  it("markExpired is IDEMPOTENT — running it twice doesn't re-process", () => {
    // Use 1ms TTL so all tickets expire by next tick.
    const q = new ApprovalQueue(1);
    const t1 = q.enqueue(INPUT);
    const t2 = q.enqueue(INPUT);
    // Fake a future time.
    const future = new Date(Date.now() + 10_000);
    const firstSweep = q.markExpired(future);
    expect(firstSweep.length).toBe(2);
    expect(firstSweep.every((t) => t.status === "expired")).toBe(true);

    // Second sweep — nothing pending past expiry remains.
    const secondSweep = q.markExpired(future);
    expect(secondSweep.length).toBe(0);
    // Tickets remain expired (not re-resolved).
    expect(q.get(t1.approvalId, "t-1").status).toBe("expired");
    expect(q.get(t2.approvalId, "t-1").status).toBe("expired");
  });

  it("approved tickets do NOT appear in listEscalations (regression)", () => {
    const q = new ApprovalQueue(1);  // immediately-expiring TTL
    const t = q.enqueue(INPUT);
    q.approve(t.approvalId, "t-1", "admin");
    const future = new Date(Date.now() + 10_000);
    const escalations = q.listEscalations(future);
    expect(escalations).toEqual([]);  // resolved tickets excluded
  });

  it("denied tickets do NOT appear in listEscalations (paired)", () => {
    const q = new ApprovalQueue(1);
    const t = q.enqueue(INPUT);
    q.deny(t.approvalId, "t-1", "admin");
    const escalations = q.listEscalations(new Date(Date.now() + 10_000));
    expect(escalations).toEqual([]);
  });

  it("BOUNDARY: ticket exactly at expiresAt is NOT yet escalated (`<` not `<=`)", () => {
    const q = new ApprovalQueue(1000);
    const t = q.enqueue(INPUT);
    // listEscalations cutoff is `now.getTime()`. Tickets where
    // expiresAt < cutoff are escalated. Exactly-at-cutoff is NOT.
    const expiryDate = new Date(t.expiresAt);
    const escalations = q.listEscalations(expiryDate);
    expect(escalations.length).toBe(0);  // expiresAt < expiresAt is false
  });

  it("BACKDOOR: pendingByWorkflow returns ONLY caller's tenant tickets", () => {
    const q = new ApprovalQueue();
    q.enqueue({ ...INPUT, tenantId: "t-A" });
    q.enqueue({ ...INPUT, tenantId: "t-A" });
    q.enqueue({ ...INPUT, tenantId: "t-B" });

    const aPending = q.pendingByWorkflow(INPUT.workflowId, "t-A");
    expect(aPending.length).toBe(2);
    expect(aPending.every((t) => t.tenantId === "t-A")).toBe(true);

    const bPending = q.pendingByWorkflow(INPUT.workflowId, "t-B");
    expect(bPending.length).toBe(1);
  });

  it("ticket carries the canonical field set after enqueue", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue(INPUT);
    expect(t.approvalId).toMatch(/^[0-9a-f-]{36}$/);
    expect(t.workflowId).toBe("wf-1");
    expect(t.stepId).toBe("s-1");
    expect(t.stepName).toBe("exec");
    expect(t.tenantId).toBe("t-1");
    expect(t.requestedBy).toBe("user-1");
    expect(t.status).toBe("pending");
    expect(t.createdAt).toBeDefined();
    expect(t.expiresAt).toBeDefined();
    expect(t.resolvedAt).toBeUndefined();
    expect(t.resolvedBy).toBeUndefined();
  });

  it("approve preserves audit metadata (resolvedAt + resolvedBy + reason)", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue(INPUT);
    const approved = q.approve(t.approvalId, "t-1", "admin@example.com", "looks fine");
    expect(approved.status).toBe("approved");
    expect(approved.resolvedAt).toBeDefined();
    expect(approved.resolvedBy).toBe("admin@example.com");
    expect(approved.reason).toBe("looks fine");
  });
});
