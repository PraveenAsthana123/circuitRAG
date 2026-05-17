// Negative drill for the P1 fix in rollback-manager.ts (2026-05-17).
//
// Pre-fix bug: RollbackManager.rollback() returned a state with
// status "rolled_back" but never saved it back. The store still
// held the popped previous state with its original status. Next
// store.get() would return inconsistent state vs what the caller saw.
//
// Test asserts the store and the caller agree post-rollback.

import { describe, it, expect } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RollbackManager } from "./rollback-manager";

describe("RollbackManager (P1 save-after-rollback fix)", () => {
  it("REGRESSION: store.get() after rollback returns 'rolled_back' status", async () => {
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(),
      new Replanner(),
      new ToolSelector(),
      new HumanApprovalGate(),
      store,
    );

    const workflow = engine.start(
      {
        workflowId: "wf-rb-1",
        requestId: "req-1",
        tenantId: "tenant-1",
        userId: "user-1",
        traceId: "trace-1",
      },
      "test rollback",
    );

    // Advance one step so history is non-empty (rollback needs at least
    // one prior version to pop).
    await engine.runNext(workflow.context.workflowId, "tenant-1");

    const returned = engine.rollback("wf-rb-1", "tenant-1", "drill test");
    expect(returned.status).toBe("rolled_back");

    // The critical regression check: store and caller must agree.
    const fromStore = store.get("wf-rb-1", "tenant-1");
    expect(fromStore.status).toBe("rolled_back");
  });

  it("rollback without history throws (RollbackManager surfaces store error)", () => {
    const store = new WorkflowStateStore();
    const mgr = new RollbackManager(store);
    // Unknown workflow throws WorkflowNotFoundError (precedes the
    // 'no history' check now that tenant authorization runs first).
    expect(() => mgr.rollback("unknown-wf", "tenant-1", "no history")).toThrow();
  });
});
