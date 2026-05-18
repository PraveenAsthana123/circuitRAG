// Negative drills for Iter 58 (2026-05-17): recovery-step depth cap.
//
// Locks the invariant that the engine refuses to insert a new
// recovery_step once `maxRecoveryDepth` recovery_steps already
// exist in the plan. Without this cap, a recovery_step that itself
// fails creates yet another recovery_step — workflow state grows
// unboundedly and the store leaks memory per failure cycle.
//
// Negative assertions:
//   1. depth==max → next failure ABANDONS workflow (no new recovery_step)
//   2. abandoned workflow's last failed step carries
//      RecoveryDepthExceededError in lastError (audit visibility)
//   3. constructor rejects negative depth
//   4. constructor rejects non-integer depth
//   5. depth==0 → ZERO replans allowed; first failure abandons
//   6. abandoned workflow returns status "failed", NOT "replanning"
//   7. positive: depth < max still permits replan (regression guard)

import { describe, it, expect } from "vitest";
import {
  AgentWorkflowEngine,
  StepOutputContext,
} from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowContext, WorkflowStep } from "./types";

class AlwaysFailEngine extends AgentWorkflowEngine {
  constructor(store: WorkflowStateStore, maxRecoveryDepth?: number) {
    super(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), store,
      maxRecoveryDepth === undefined ? {} : { maxRecoveryDepth },
    );
  }
  protected async simulateToolExecution(
    _toolName: string,
    _ctx: StepOutputContext,
    _step: WorkflowStep,
  ): Promise<unknown> {
    throw new Error("permanent: schema mismatch");
  }
}

const CTX: WorkflowContext = {
  workflowId: "wf-rd", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

function countRecovery(steps: WorkflowStep[]): number {
  return steps.filter((s) => s.name === "recovery_step").length;
}

describe("AgentWorkflowEngine — recovery depth cap (P1)", () => {
  it("BACKDOOR CHECK: hitting maxRecoveryDepth abandons workflow (no further recovery_step)", async () => {
    const store = new WorkflowStateStore();
    const engine = new AlwaysFailEngine(store, 2);
    const wf = engine.start({ ...CTX, workflowId: "wf-rd-1" }, "test");

    // 1st runNext: step 0 fails → 1st recovery_step added (depth=1).
    const after1 = await engine.runNext(wf.context.workflowId, "t");
    expect(after1.status).toBe("replanning");
    expect(countRecovery(after1.steps)).toBe(1);

    // 2nd runNext: recovery_step (now currentStepIndex) fails → 2nd
    // recovery_step added (depth=2).
    const after2 = await engine.runNext(wf.context.workflowId, "t");
    expect(after2.status).toBe("replanning");
    expect(countRecovery(after2.steps)).toBe(2);

    // 3rd runNext: depth already == max (2). Engine MUST abandon
    // instead of inserting a 3rd recovery_step.
    const after3 = await engine.runNext(wf.context.workflowId, "t");
    expect(after3.status).toBe("failed");
    expect(countRecovery(after3.steps)).toBe(2);  // unchanged
  });

  it("BACKDOOR CHECK: abandoned workflow's failed step carries RecoveryDepthExceededError", async () => {
    const store = new WorkflowStateStore();
    const engine = new AlwaysFailEngine(store, 1);
    const wf = engine.start({ ...CTX, workflowId: "wf-rd-2" }, "test");

    await engine.runNext(wf.context.workflowId, "t");  // depth=1
    const after = await engine.runNext(wf.context.workflowId, "t");  // abandon

    expect(after.status).toBe("failed");
    const failedRecovery = after.steps[after.currentStepIndex];
    expect(failedRecovery.status).toBe("failed");
    expect(failedRecovery.lastError).toBeDefined();
    expect(failedRecovery.lastError!.name).toBe("RecoveryDepthExceededError");
    expect(failedRecovery.lastError!.message).toContain("Recovery depth");
    expect(failedRecovery.lastError!.message).toContain("abandoned");
    expect(failedRecovery.lastError!.retryable).toBe(false);
  });

  it("constructor rejects negative maxRecoveryDepth", () => {
    const store = new WorkflowStateStore();
    expect(() => new AlwaysFailEngine(store, -1)).toThrow(/maxRecoveryDepth/);
  });

  it("constructor rejects non-integer maxRecoveryDepth", () => {
    const store = new WorkflowStateStore();
    expect(() => new AlwaysFailEngine(store, 1.5)).toThrow(/maxRecoveryDepth/);
  });

  it("maxRecoveryDepth=0 abandons on the FIRST failure (no replan attempt)", async () => {
    const store = new WorkflowStateStore();
    const engine = new AlwaysFailEngine(store, 0);
    const wf = engine.start({ ...CTX, workflowId: "wf-rd-3" }, "test");

    const after = await engine.runNext(wf.context.workflowId, "t");
    expect(after.status).toBe("failed");
    expect(countRecovery(after.steps)).toBe(0);
    const failed = after.steps[0];
    expect(failed.status).toBe("failed");
    expect(failed.lastError!.name).toBe("RecoveryDepthExceededError");
  });

  it("abandoned workflow status is 'failed', NOT 'replanning' (regression)", async () => {
    // This is the workflow-level invariant: replanning means "we are
    // still trying", failed means "we gave up". Conflating them is
    // exactly the bug iter 58 prevents.
    const store = new WorkflowStateStore();
    const engine = new AlwaysFailEngine(store, 0);
    const wf = engine.start({ ...CTX, workflowId: "wf-rd-4" }, "test");
    const after = await engine.runNext(wf.context.workflowId, "t");
    expect(after.status).not.toBe("replanning");
    expect(after.status).toBe("failed");
  });

  it("depth < max still allows replan (regression guard for happy path)", async () => {
    const store = new WorkflowStateStore();
    const engine = new AlwaysFailEngine(store, 5);
    const wf = engine.start({ ...CTX, workflowId: "wf-rd-5" }, "test");

    // Three failures, depth becomes 1, 2, 3 — all replan, none abandon.
    for (let i = 0; i < 3; i++) {
      const s = await engine.runNext(wf.context.workflowId, "t");
      expect(s.status).toBe("replanning");
    }
    const final = store.get(wf.context.workflowId, "t");
    expect(countRecovery(final.steps)).toBe(3);
  });

  it("default depth (3) blocks the 4th replan attempt", async () => {
    // No depth passed → engine uses DEFAULT_MAX_RECOVERY_DEPTH = 3.
    const store = new WorkflowStateStore();
    const engine = new AlwaysFailEngine(store);  // no override
    const wf = engine.start({ ...CTX, workflowId: "wf-rd-6" }, "test");

    // Failures 1, 2, 3 → replan (depths 1, 2, 3).
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");
    // Failure 4 → depth already 3, abandon.
    const final = await engine.runNext(wf.context.workflowId, "t");
    expect(final.status).toBe("failed");
    expect(countRecovery(final.steps)).toBe(3);
  });
});
