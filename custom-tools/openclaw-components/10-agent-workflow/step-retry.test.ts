// Negative drills for Iter 44 (2026-05-17): step retry vs replan
// distinction.

import { describe, it, expect } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RetryableError, WorkflowState, WorkflowContext } from "./types";

/** Test subclass that lets us script per-call behavior of the
 *  underlying tool execution. */
class ScriptedEngine extends AgentWorkflowEngine {
  public attempts = 0;
  constructor(
    private readonly script: ((attempt: number) => Promise<void>),
    store: WorkflowStateStore,
  ) {
    super(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), store,
    );
  }
  protected async simulateToolExecution(_toolName: string): Promise<void> {
    this.attempts += 1;
    return this.script(this.attempts);
  }
}

const CTX: WorkflowContext = {
  workflowId: "wf-retry", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

function attachMaxRetries(state: WorkflowState, max: number) {
  for (const s of state.steps) s.maxRetries = max;
}

describe("AgentWorkflowEngine — step retry vs replan (P1)", () => {
  it("BACKDOOR CHECK: transient RetryableError retries the SAME step", async () => {
    let attempts = 0;
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      attempts = n;
      if (n === 1) throw new RetryableError("transient blip");
    }, store);

    const wf = engine.start(CTX, "test");
    // Configure step 0 to allow up to 3 retries.
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 3;
    store.save(initial);

    // 1st runNext: throws RetryableError → marked pending again,
    // currentStepIndex unchanged.
    const afterFirst = await engine.runNext(wf.context.workflowId, "t");
    expect(afterFirst.currentStepIndex).toBe(0);
    expect(afterFirst.steps[0].retryCount).toBe(1);
    expect(afterFirst.status).toBe("executing");

    // 2nd runNext: tool succeeds, step completes, index advances.
    const afterSecond = await engine.runNext(wf.context.workflowId, "t");
    expect(afterSecond.currentStepIndex).toBe(1);
    expect(attempts).toBe(2);
  });

  it("non-RetryableError goes straight to replan (no retry)", async () => {
    let attempts = 0;
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      attempts = n;
      throw new Error("permanent: schema mismatch");
    }, store);

    const wf = engine.start(CTX, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 5;  // even with retries available,
    store.save(initial);              // a non-Retryable shouldn't retry.

    const after = await engine.runNext(wf.context.workflowId, "t");
    expect(after.status).toBe("replanning");
    expect(attempts).toBe(1);
  });

  it("non-RetryableError replans to execute the recovery step next", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("permanent: schema mismatch");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-replan-order" }, "test");
    const after = await engine.runNext(wf.context.workflowId, "t");

    expect(after.status).toBe("replanning");
    expect(after.steps[after.currentStepIndex].name).toBe("recovery_step");
    expect(after.steps[after.currentStepIndex].status).toBe("pending");
    expect(after.steps[after.currentStepIndex - 1].status).toBe("failed");
  });

  it("RetryableError beyond maxRetries falls through to replan", async () => {
    let attempts = 0;
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      attempts = n;
      throw new RetryableError("always fails");
    }, store);

    const wf = engine.start(CTX, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 2;
    store.save(initial);

    // Three runNexts: try 1 → retry, try 2 → retry, try 3 → replan.
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");
    const final = await engine.runNext(wf.context.workflowId, "t");
    expect(final.status).toBe("replanning");
    expect(attempts).toBe(3);
  });

  it("backcompat: step with no maxRetries (or 0) does not retry", async () => {
    let attempts = 0;
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      attempts = n;
      throw new RetryableError("blip");
    }, store);

    const wf = engine.start(CTX, "test");
    // Default maxRetries undefined; pre-fix behavior preserved.
    const after = await engine.runNext(wf.context.workflowId, "t");
    expect(after.status).toBe("replanning");
    expect(attempts).toBe(1);
  });
});
