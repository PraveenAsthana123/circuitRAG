// Negative drills for Iter 57 (2026-05-17): step error envelope.
//
// Locks the invariant that when a step throws, a StepErrorEnvelope:
//   1. Is persisted on the step.
//   2. Carries name + message + retryable flag + timestamp.
//   3. Carries stack on real Error instances (when the engine has it).
//   4. Survives the replan copy (replanner.replan preserves the
//      `{...failedStep, status: "failed"}` shape — lastError rides
//      along).
//   5. Is overwritten on each subsequent retry (not appended — the
//      MOST RECENT failure is what matters for triage).
//   6. Is cleared to undefined on eventual success (no leftover
//      error masquerading as a "completed with error" record).
//   7. Handles non-Error throws (string, number, undefined) without
//      crashing the engine.

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

class ScriptedEngine extends AgentWorkflowEngine {
  public attempts = 0;
  constructor(
    private readonly script: (attempt: number) => Promise<unknown>,
    store: WorkflowStateStore,
  ) {
    super(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), store,
    );
  }
  protected async simulateToolExecution(
    _toolName: string,
    _ctx: StepOutputContext,
    _step: WorkflowStep,
  ): Promise<unknown> {
    this.attempts += 1;
    return this.script(this.attempts);
  }
}

const CTX: WorkflowContext = {
  workflowId: "wf-err", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

describe("AgentWorkflowEngine — step error envelope (P1)", () => {
  it("BACKDOOR CHECK: retry captures envelope with name + message + retryable + timestamp", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      if (n === 1) throw new RetryableError("transient blip");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-err-1" }, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 2;
    store.save(initial);

    await engine.runNext(wf.context.workflowId, "t");  // throws → retry
    const afterRetry = store.get(wf.context.workflowId, "t");

    const err = afterRetry.steps[0].lastError;
    expect(err).toBeDefined();
    expect(err!.name).toBe("RetryableError");
    expect(err!.message).toBe("transient blip");
    expect(err!.retryable).toBe(true);
    // ISO-8601 timestamp parses without throwing.
    expect(() => new Date(err!.timestamp).toISOString()).not.toThrow();
    // Real Error → stack present (engine builds + Node always populate).
    expect(err!.stack).toBeDefined();
    expect(err!.stack).toContain("RetryableError");
  });

  it("BACKDOOR CHECK: lastError SURVIVES the replan copy", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("permanent: schema mismatch");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-err-2" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const after = store.get(wf.context.workflowId, "t");
    // Step 0 was preserved as 'failed' by the replanner.
    const failed = after.steps[0];
    expect(failed.status).toBe("failed");
    // lastError rode through `{...failedStep, status: "failed"}`.
    expect(failed.lastError).toBeDefined();
    expect(failed.lastError!.name).toBe("Error");
    expect(failed.lastError!.message).toBe("permanent: schema mismatch");
    expect(failed.lastError!.retryable).toBe(false);
  });

  it("non-RetryableError records retryable: false", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new TypeError("bad type");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-err-3" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].lastError!.name).toBe("TypeError");
    expect(after.steps[0].lastError!.retryable).toBe(false);
  });

  it("each retry OVERWRITES lastError (no leftover from earlier attempt)", async () => {
    const store = new WorkflowStateStore();
    let n = 0;
    const engine = new ScriptedEngine(async () => {
      n += 1;
      throw new RetryableError(`attempt-${n}-failed`);
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-err-4" }, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 3;
    store.save(initial);

    await engine.runNext(wf.context.workflowId, "t");  // attempt 1
    await engine.runNext(wf.context.workflowId, "t");  // attempt 2
    const mid = store.get(wf.context.workflowId, "t");
    expect(mid.steps[0].lastError!.message).toBe("attempt-2-failed");

    await engine.runNext(wf.context.workflowId, "t");  // attempt 3
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].lastError!.message).toBe("attempt-3-failed");
  });

  it("lastError is CLEARED when a retry eventually succeeds", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      if (n === 1) throw new RetryableError("blip");
      return { ok: true };
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-err-5" }, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 2;
    store.save(initial);

    await engine.runNext(wf.context.workflowId, "t");  // throws → retry, lastError set
    const mid = store.get(wf.context.workflowId, "t");
    expect(mid.steps[0].lastError).toBeDefined();

    await engine.runNext(wf.context.workflowId, "t");  // succeeds → lastError cleared
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("completed");
    expect(after.steps[0].lastError).toBeUndefined();
  });

  it("non-Error throws (string) do NOT crash the engine — envelope name='NonError'", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw "string-not-error";
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-err-6" }, "test");
    const after = await engine.runNext(wf.context.workflowId, "t");
    expect(after.status).toBe("replanning");
    const persisted = store.get(wf.context.workflowId, "t");
    const err = persisted.steps[0].lastError;
    expect(err).toBeDefined();
    expect(err!.name).toBe("NonError");
    expect(err!.message).toBe("string-not-error");
    expect(err!.retryable).toBe(false);
    expect(err!.stack).toBeUndefined();
  });

  it("first-success path leaves lastError undefined (no leak from prior workflow state)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => ({ ok: true }), store);
    const wf = engine.start({ ...CTX, workflowId: "wf-err-7" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("completed");
    expect(after.steps[0].lastError).toBeUndefined();
  });
});
