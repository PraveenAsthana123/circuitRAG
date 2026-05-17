// Negative drill for Iteration 8 (2026-05-17):
// WorkflowStateStore tenant isolation (P0 GAPS Component 10 row 8).
//
// Pre-fix: any caller with a workflowId could read or rollback any
// tenant's workflow because store.get/rollback never checked tenant.
// Now: callerTenantId is required; mismatch throws
// WorkflowAccessDeniedError.

import { describe, it, expect } from "vitest";
import {
  WorkflowStateStore,
  WorkflowAccessDeniedError,
  WorkflowNotFoundError,
} from "./workflow-state-store";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";

function buildEngine() {
  const store = new WorkflowStateStore();
  const engine = new AgentWorkflowEngine(
    new WorkflowPlanner(),
    new Replanner(),
    new ToolSelector(),
    new HumanApprovalGate(),
    store,
  );
  return { store, engine };
}

describe("WorkflowStateStore — tenant isolation (P0)", () => {
  it("store.get with WRONG tenantId throws AccessDenied (BACKDOOR CHECK)", () => {
    const { store, engine } = buildEngine();
    engine.start(
      {
        workflowId: "wf-iso-1",
        requestId: "r", tenantId: "tenant-A", userId: "u", traceId: "tr",
      },
      "x",
    );

    // Owner can read.
    expect(() => store.get("wf-iso-1", "tenant-A")).not.toThrow();

    // Cross-tenant read is denied.
    expect(() => store.get("wf-iso-1", "tenant-B"))
      .toThrowError(WorkflowAccessDeniedError);
  });

  it("store.rollback with WRONG tenantId throws AccessDenied", async () => {
    const { store, engine } = buildEngine();
    engine.start(
      {
        workflowId: "wf-iso-2",
        requestId: "r", tenantId: "tenant-A", userId: "u", traceId: "tr",
      },
      "x",
    );
    await engine.runNext("wf-iso-2", "tenant-A"); // populate history

    expect(() => store.rollback("wf-iso-2", "tenant-B"))
      .toThrowError(WorkflowAccessDeniedError);
  });

  it("store.get with unknown workflowId throws NotFound (regardless of tenant)", () => {
    const { store } = buildEngine();
    expect(() => store.get("does-not-exist", "tenant-A"))
      .toThrowError(WorkflowNotFoundError);
  });

  it("save() rejects re-saving same workflowId with a different tenantId", () => {
    const { store, engine } = buildEngine();
    engine.start(
      {
        workflowId: "wf-iso-3",
        requestId: "r", tenantId: "tenant-A", userId: "u", traceId: "tr",
      },
      "x",
    );

    // Attempt to hijack the workflow by re-saving with tenant-B.
    const hijack = {
      context: {
        workflowId: "wf-iso-3",
        requestId: "r", tenantId: "tenant-B", userId: "u", traceId: "tr",
      },
      status: "executing" as const,
      userGoal: "hijack",
      steps: [],
      currentStepIndex: 0,
      createdAt: "2026-05-17T00:00:00.000Z",
      updatedAt: "2026-05-17T00:00:00.000Z",
    };
    expect(() => store.save(hijack)).toThrowError(WorkflowAccessDeniedError);
  });

  it("engine.runNext also enforces tenant", async () => {
    const { engine } = buildEngine();
    engine.start(
      {
        workflowId: "wf-iso-4",
        requestId: "r", tenantId: "tenant-A", userId: "u", traceId: "tr",
      },
      "x",
    );

    await expect(engine.runNext("wf-iso-4", "tenant-B"))
      .rejects.toThrowError(WorkflowAccessDeniedError);
  });

  it("engine.rollback also enforces tenant", async () => {
    const { engine } = buildEngine();
    engine.start(
      {
        workflowId: "wf-iso-5",
        requestId: "r", tenantId: "tenant-A", userId: "u", traceId: "tr",
      },
      "x",
    );
    await engine.runNext("wf-iso-5", "tenant-A"); // populate history

    expect(() => engine.rollback("wf-iso-5", "tenant-B", "drill"))
      .toThrowError(WorkflowAccessDeniedError);
  });
});
