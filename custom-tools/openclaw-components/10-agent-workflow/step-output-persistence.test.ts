// Negative drills for Iter 55 (2026-05-17): step output persistence.
//
// Locks the invariant that a successful step's return value is:
//   1. Persisted on the WorkflowStep via `output`.
//   2. Readable by a downstream step through StepOutputContext.
//   3. Cleared on retry (no stale value leaks into a rerun).
//   4. Cleared on permanent failure (no stale value leaks past replan).
//   5. Invisible across tenant boundaries (no cross-tenant leak).
//   6. NOT readable from the same-step or future-step (only upstream
//      *completed* steps contribute to the context).

import { describe, it, expect } from "vitest";
import { AgentWorkflowEngine, StepOutputContext } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import {
  RetryableError,
  WorkflowContext,
  WorkflowStep,
} from "./types";

/** Test subclass that lets us script per-step behaviour AND inspect
 *  what each tool saw via outputContext. */
class ScriptedEngine extends AgentWorkflowEngine {
  public seen: Array<{ stepName: string; upstream: Record<string, unknown> }> = [];
  constructor(
    private readonly script: (
      attempt: number,
      stepName: string,
      ctx: StepOutputContext,
    ) => Promise<unknown>,
    store: WorkflowStateStore,
  ) {
    super(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), store,
    );
  }
  public attempts = 0;
  protected async simulateToolExecution(
    _toolName: string,
    ctx: StepOutputContext,
    step: WorkflowStep,
  ): Promise<unknown> {
    this.attempts += 1;
    // Snapshot what THIS step could see from upstream completed steps.
    this.seen.push({
      stepName: step.name,
      upstream: {
        understand_goal: ctx.getByName("understand_goal"),
        select_tools: ctx.getByName("select_tools"),
        execute_task: ctx.getByName("execute_task"),
      },
    });
    return this.script(this.attempts, step.name, ctx);
  }
}

const CTX: WorkflowContext = {
  workflowId: "wf-output", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

describe("AgentWorkflowEngine — step output persistence (P1)", () => {
  it("BACKDOOR CHECK: successful step persists its output on the step", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (_n, name) => {
      if (name === "understand_goal") return { intent: "summarize" };
      return undefined;
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-1" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    // Read state back through the store — round-trips structuredClone.
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("completed");
    expect(after.steps[0].output).toEqual({ intent: "summarize" });
  });

  it("BACKDOOR CHECK: downstream step reads upstream output", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (_n, name) => {
      if (name === "understand_goal") return { intent: "summarize" };
      if (name === "select_tools") return ["summarizer"];
      return undefined;
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-2" }, "test");
    await engine.runNext(wf.context.workflowId, "t");  // step 0
    await engine.runNext(wf.context.workflowId, "t");  // step 1
    await engine.runNext(wf.context.workflowId, "t");  // step 2

    // Step 2 (execute_task) must have seen BOTH prior outputs.
    const step2View = engine.seen.find((s) => s.stepName === "execute_task");
    expect(step2View).toBeDefined();
    expect(step2View!.upstream.understand_goal).toEqual({ intent: "summarize" });
    expect(step2View!.upstream.select_tools).toEqual(["summarizer"]);
  });

  it("step cannot see its OWN output (only strictly-upstream contribute)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (_n, name) => {
      if (name === "understand_goal") return "self-value";
      return undefined;
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-3" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    // During step 0 execution, ctx.getByName("understand_goal") MUST
    // have been undefined — it hadn't completed yet.
    const step0View = engine.seen[0];
    expect(step0View.stepName).toBe("understand_goal");
    expect(step0View.upstream.understand_goal).toBeUndefined();
  });

  it("retry clears stale output (no leak from failed-and-retried attempt)", async () => {
    const store = new WorkflowStateStore();
    // Step 0: 1st attempt throws RetryableError, 2nd attempt succeeds
    // with a DIFFERENT value than what a buggy implementation might
    // have leaked from the (non-existent) first-success path.
    const engine = new ScriptedEngine(async (n) => {
      if (n === 1) throw new RetryableError("blip");
      return { final: true };
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-4" }, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 2;
    store.save(initial);

    // 1st runNext: throws, retried, status → pending, output cleared.
    await engine.runNext(wf.context.workflowId, "t");
    const afterRetry = store.get(wf.context.workflowId, "t");
    expect(afterRetry.steps[0].status).toBe("pending");
    expect(afterRetry.steps[0].output).toBeUndefined();
    expect(afterRetry.steps[0].retryCount).toBe(1);

    // 2nd runNext: succeeds, output set to the SECOND attempt's value.
    await engine.runNext(wf.context.workflowId, "t");
    const afterSuccess = store.get(wf.context.workflowId, "t");
    expect(afterSuccess.steps[0].status).toBe("completed");
    expect(afterSuccess.steps[0].output).toEqual({ final: true });
  });

  it("permanent failure (replan) does NOT persist output", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("permanent: schema mismatch");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-5" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("failed");
    expect(after.steps[0].output).toBeUndefined();
  });

  it("output context excludes failed/pending upstream steps", async () => {
    // Force step 0 to fail (replan). Then the replanned 'recovery_step'
    // runs as the new step at currentStepIndex — its output context
    // must NOT show step 0's output (it has none — it failed).
    const store = new WorkflowStateStore();
    let throwCount = 0;
    const engine = new ScriptedEngine(async (_n, name) => {
      if (name === "understand_goal" && throwCount === 0) {
        throwCount += 1;
        throw new Error("permanent fail");
      }
      return { ran: name };
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-6" }, "test");
    await engine.runNext(wf.context.workflowId, "t");   // step 0 fails → replan
    await engine.runNext(wf.context.workflowId, "t");   // recovery_step runs

    const recoveryView = engine.seen.find((s) => s.stepName === "recovery_step");
    expect(recoveryView).toBeDefined();
    // understand_goal failed; its output MUST be undefined in the
    // downstream context — failed steps don't contribute.
    expect(recoveryView!.upstream.understand_goal).toBeUndefined();
  });

  it("output is NOT readable across tenants (multi-tenant isolation)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => "tenant-A-secret", store);

    const wfA = engine.start(
      { ...CTX, workflowId: "wf-out-A", tenantId: "tenant-A" },
      "test-A",
    );
    await engine.runNext(wfA.context.workflowId, "tenant-A");

    // Tenant B asking for tenant A's workflow → access denied at store.
    expect(() => store.get(wfA.context.workflowId, "tenant-B")).toThrow(
      /cannot access workflow/,
    );
  });

  it("output survives a save → get round trip (structuredClone preserves shape)", async () => {
    const store = new WorkflowStateStore();
    const richOutput = {
      nested: { array: [1, 2, 3], map: { k: "v" } },
      flag: true,
      n: 42,
    };
    const engine = new ScriptedEngine(async () => richOutput, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-out-7" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const after = store.get(wf.context.workflowId, "t");
    // Deep-equal but NOT the same reference — structuredClone defended
    // against mutation by the caller.
    expect(after.steps[0].output).toEqual(richOutput);
    expect(after.steps[0].output).not.toBe(richOutput);
  });
});
