// Negative drills for Iter 22 (2026-05-17): ApprovalQueue +
// HumanApprovalGate durability.

import { describe, it, expect } from "vitest";
import {
  ApprovalQueue,
  ApprovalAccessDeniedError,
  ApprovalAlreadyResolvedError,
  ApprovalNotFoundError,
} from "./approval-queue";
import { HumanApprovalGate } from "./human-approval";

describe("ApprovalQueue (P0 — durable replacement for console.log)", () => {
  it("BACKDOOR CHECK: enqueue persists the ticket and exposes status", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue({
      workflowId: "w1", stepId: "s1", stepName: "deploy",
      tenantId: "tenant-A", requestedBy: "u1",
    });
    expect(t.status).toBe("pending");
    expect(q.get(t.approvalId, "tenant-A").status).toBe("pending");
  });

  it("tenant isolation: cross-tenant read denied", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue({
      workflowId: "w1", stepId: "s1", stepName: "x",
      tenantId: "tenant-A", requestedBy: "u",
    });
    expect(() => q.get(t.approvalId, "tenant-B"))
      .toThrowError(ApprovalAccessDeniedError);
  });

  it("approve transitions pending → approved exactly once", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue({
      workflowId: "w1", stepId: "s1", stepName: "x",
      tenantId: "tenant-A", requestedBy: "u",
    });
    const approved = q.approve(t.approvalId, "tenant-A", "admin@example.com");
    expect(approved.status).toBe("approved");
    expect(approved.resolvedBy).toBe("admin@example.com");

    // Idempotency / double-approve check.
    expect(() => q.approve(t.approvalId, "tenant-A", "admin@example.com"))
      .toThrowError(ApprovalAlreadyResolvedError);
  });

  it("deny works symmetrically", () => {
    const q = new ApprovalQueue();
    const t = q.enqueue({
      workflowId: "w1", stepId: "s1", stepName: "x",
      tenantId: "tenant-A", requestedBy: "u",
    });
    const denied = q.deny(t.approvalId, "tenant-A", "sec@example.com", "policy violation");
    expect(denied.status).toBe("denied");
    expect(denied.reason).toBe("policy violation");
  });

  it("expired tickets surface via listEscalations", () => {
    const q = new ApprovalQueue(10 /* ttlMs */);
    const t = q.enqueue({
      workflowId: "w1", stepId: "s1", stepName: "x",
      tenantId: "tenant-A", requestedBy: "u",
    });
    // Fast-forward via custom Date
    const future = new Date(Date.now() + 60_000);
    const esc = q.listEscalations(future);
    expect(esc.find((e) => e.approvalId === t.approvalId)).toBeTruthy();

    const marked = q.markExpired(future);
    expect(marked[0].status).toBe("expired");
    expect(q.get(t.approvalId, "tenant-A").status).toBe("expired");
  });

  it("pendingByWorkflow returns only this tenant's pending tickets", () => {
    const q = new ApprovalQueue();
    q.enqueue({
      workflowId: "w1", stepId: "s1", stepName: "x",
      tenantId: "tenant-A", requestedBy: "u",
    });
    q.enqueue({
      workflowId: "w1", stepId: "s2", stepName: "x",
      tenantId: "tenant-B", requestedBy: "u",
    });
    const aPending = q.pendingByWorkflow("w1", "tenant-A");
    expect(aPending.length).toBe(1);
    expect(aPending[0].tenantId).toBe("tenant-A");
  });

  it("get on unknown approvalId throws NotFound", () => {
    const q = new ApprovalQueue();
    expect(() => q.get("missing", "tenant-A"))
      .toThrowError(ApprovalNotFoundError);
  });
});

describe("HumanApprovalGate wraps the queue", () => {
  it("requestApproval returns the queue ticket id, persists in queue", () => {
    const queue = new ApprovalQueue();
    const gate = new HumanApprovalGate(queue);
    const id = gate.requestApproval(
      {
        workflowId: "w", requestId: "r",
        tenantId: "tenant-A", userId: "u", traceId: "tr",
      },
      {
        stepId: "s", name: "deploy", goal: "g",
        requiresApproval: true, status: "pending",
      },
    );
    expect(queue.get(id, "tenant-A").status).toBe("pending");
  });
});
