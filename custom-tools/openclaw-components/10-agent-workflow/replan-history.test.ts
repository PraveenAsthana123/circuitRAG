// Negative drills for Iter 66 (2026-05-17): workflow-level
// replan-history audit row.
//
// Locks the invariant that the engine appends a structured
// ReplanHistoryEntry to WorkflowState.replanHistory on every TRUE
// replan event:
//   1. Non-retryable failure → replan path → entry appended.
//   2. Retryable failure exhausting maxRetries → replan path → entry.
//   3. Recovery-depth cap exceeded → abandon path → final entry
//      with RecoveryDepthExceededError (operator sees "we gave up").
// AND that NO entry is appended on:
//   - Same-step retry (RetryableError within budget).
//   - Successful step execution.
//
// Negative assertions (≥6):
//   1. BACKDOOR: first failure adds entry with correct failedStepId
//      + failedStepName + errorName + errorMessage.
//   2. BACKDOOR: subsequent replans append (length grows 1 → 2 → 3).
//   3. Abandoned workflow's FINAL entry carries
//      RecoveryDepthExceededError (audit visibility for "gave up").
//   4. Successful workflow leaves replanHistory undefined or [].
//   5. Retry-then-success leaves replanHistory empty (true-replan-only
//      rule — bare retries do NOT pollute the history).
//   6. recoveryDepthAtTime reflects depth WHEN entry was added
//      (0 on first replan, grows as recovery_steps accumulate).
//   7. Entries SURVIVE structuredClone via the store's save → get
//      round-trip (otherwise the history disappears on every save).

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
    maxRecoveryDepth?: number,
  ) {
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
    this.attempts += 1;
    return this.script(this.attempts);
  }
}

const CTX: WorkflowContext = {
  workflowId: "wf-rh",
  requestId: "r",
  tenantId: "t",
  userId: "u",
  traceId: "tr",
};

describe("AgentWorkflowEngine — workflow replan-history audit (P1)", () => {
  it("BACKDOOR CHECK: first non-retryable failure appends entry with stepId + stepName + errorName + errorMessage", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("permanent: schema mismatch");
    }, store, 3);

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-1" }, "test");
    const initialStepId = wf.steps[0].stepId;
    const initialStepName = wf.steps[0].name;

    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");

    expect(after.replanHistory).toBeDefined();
    expect(after.replanHistory!.length).toBe(1);
    const entry = after.replanHistory![0];
    expect(entry.failedStepId).toBe(initialStepId);
    expect(entry.failedStepName).toBe(initialStepName);
    expect(entry.errorName).toBe("Error");
    expect(entry.errorMessage).toBe("permanent: schema mismatch");
    expect(entry.retryable).toBe(false);
    // recoveryDepthAtTime: this is the FIRST replan; no recovery_step
    // existed before — depth was 0 when the entry was created.
    expect(entry.recoveryDepthAtTime).toBe(0);
    // ISO-8601 timestamp parses.
    expect(() => new Date(entry.timestamp).toISOString()).not.toThrow();
  });

  it("BACKDOOR CHECK: each subsequent replan APPENDS another entry (length grows 1 → 2 → 3)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("always fails");
    }, store, 5);  // generous cap so we can observe pure-replan growth

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-2" }, "test");

    await engine.runNext(wf.context.workflowId, "t");
    let after = store.get(wf.context.workflowId, "t");
    expect(after.replanHistory!.length).toBe(1);
    expect(after.replanHistory![0].recoveryDepthAtTime).toBe(0);

    await engine.runNext(wf.context.workflowId, "t");
    after = store.get(wf.context.workflowId, "t");
    expect(after.replanHistory!.length).toBe(2);
    expect(after.replanHistory![1].recoveryDepthAtTime).toBe(1);

    await engine.runNext(wf.context.workflowId, "t");
    after = store.get(wf.context.workflowId, "t");
    expect(after.replanHistory!.length).toBe(3);
    expect(after.replanHistory![2].recoveryDepthAtTime).toBe(2);
  });

  it("abandoned workflow's FINAL entry carries RecoveryDepthExceededError (audit 'we gave up')", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("permanent");
    }, store, 1);  // cap = 1 → 2nd failure abandons

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-3" }, "test");

    await engine.runNext(wf.context.workflowId, "t");  // depth → 1, replan
    const afterReplan = store.get(wf.context.workflowId, "t");
    expect(afterReplan.replanHistory!.length).toBe(1);
    expect(afterReplan.replanHistory![0].errorName).toBe("Error");

    const abandoned = await engine.runNext(wf.context.workflowId, "t");
    expect(abandoned.status).toBe("failed");

    const final = store.get(wf.context.workflowId, "t");
    // 1 prior replan + 1 abandon entry = 2 total.
    expect(final.replanHistory!.length).toBe(2);
    const last = final.replanHistory![final.replanHistory!.length - 1];
    expect(last.errorName).toBe("RecoveryDepthExceededError");
    expect(last.errorMessage).toContain("Recovery depth");
    expect(last.errorMessage).toContain("abandoned");
    expect(last.retryable).toBe(false);
    // Depth that triggered the abandon was the cap (1) — that IS
    // the depth the engine saw when it gave up.
    expect(last.recoveryDepthAtTime).toBe(1);
  });

  it("successful workflow leaves replanHistory undefined or empty (no replans → no audit row)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => ({ ok: true }), store);
    const wf = engine.start({ ...CTX, workflowId: "wf-rh-4" }, "test");

    // Run all 4 default-plan steps; each succeeds.
    for (let i = 0; i < 4; i++) {
      await engine.runNext(wf.context.workflowId, "t");
    }
    // One more runNext to bump status → "completed".
    await engine.runNext(wf.context.workflowId, "t");

    const final = store.get(wf.context.workflowId, "t");
    expect(final.status).toBe("completed");
    // Either undefined or an empty array — both mean "no replans".
    const history = final.replanHistory ?? [];
    expect(history.length).toBe(0);
  });

  it("retry-then-success leaves replanHistory empty (true-replan-only rule)", async () => {
    // RetryableError WITHIN maxRetries budget must NOT append to
    // replanHistory — only true replans count. If a step retries
    // and then succeeds, the audit has nothing to record at the
    // workflow level (the lastError ledger covers the retry detail).
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async (n) => {
      if (n === 1) throw new RetryableError("transient blip");
      return undefined;
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-5" }, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 2;
    store.save(initial);

    await engine.runNext(wf.context.workflowId, "t");  // throws → retry
    await engine.runNext(wf.context.workflowId, "t");  // succeeds

    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("completed");
    const history = after.replanHistory ?? [];
    expect(history.length).toBe(0);
  });

  it("recoveryDepthAtTime reflects depth WHEN the entry was added (not later)", async () => {
    // After three replans the plan contains three recovery_steps.
    // The first entry's recoveryDepthAtTime must still read 0
    // (the depth when IT was created), not 3 (the depth after).
    // This invariant is what makes the audit chronologically honest.
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("perm");
    }, store, 5);

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-6" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");

    expect(after.replanHistory!.length).toBe(3);
    // Each entry captures the depth at its OWN write time.
    expect(after.replanHistory![0].recoveryDepthAtTime).toBe(0);
    expect(after.replanHistory![1].recoveryDepthAtTime).toBe(1);
    expect(after.replanHistory![2].recoveryDepthAtTime).toBe(2);
  });

  it("entries survive save → get round-trip via structuredClone (audit doesn't vanish on persist)", async () => {
    // If replanHistory were dropped by the store's structuredClone
    // or by `...state` spreads anywhere in the pipeline, the audit
    // would silently disappear between runNext() calls. Drill that
    // a write followed by a fresh read returns the same entries.
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("perm");
    }, store, 5);

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-7" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");

    // Read TWICE via the store — each get() does its own
    // structuredClone. Both must produce the same audit shape.
    const read1 = store.get(wf.context.workflowId, "t");
    const read2 = store.get(wf.context.workflowId, "t");

    expect(read1.replanHistory).toBeDefined();
    expect(read2.replanHistory).toBeDefined();
    expect(read1.replanHistory!.length).toBe(2);
    expect(read2.replanHistory!.length).toBe(2);
    // Round-trip equality on each entry's content.
    for (let i = 0; i < read1.replanHistory!.length; i++) {
      expect(read1.replanHistory![i]).toEqual(read2.replanHistory![i]);
    }
    // And mutating one read does NOT bleed into the next read
    // (structuredClone isolates them).
    read1.replanHistory!.push({
      timestamp: "x",
      failedStepId: "x",
      failedStepName: "x",
      errorName: "x",
      errorMessage: "x",
      retryable: false,
      recoveryDepthAtTime: 999,
    });
    const read3 = store.get(wf.context.workflowId, "t");
    expect(read3.replanHistory!.length).toBe(2);  // unchanged
  });

  it("RETRY (within budget) does NOT append a replan-history entry — only the EVENTUAL replan does", async () => {
    // Pair-with-prior assertion: a RetryableError that EVENTUALLY
    // exhausts the budget and falls into the replan path should
    // produce exactly ONE entry — not one per retry attempt.
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new RetryableError("always-transient");
    }, store, 5);

    const wf = engine.start({ ...CTX, workflowId: "wf-rh-8" }, "test");
    const initial = store.get(wf.context.workflowId, "t");
    initial.steps[0].maxRetries = 2;
    store.save(initial);

    // 1st runNext → throw → retry (retryCount 1, no replan, no entry).
    await engine.runNext(wf.context.workflowId, "t");
    let mid = store.get(wf.context.workflowId, "t");
    expect(mid.replanHistory ?? []).toEqual([]);  // no entry yet

    // 2nd runNext → throw → retry (retryCount 2, no replan, no entry).
    await engine.runNext(wf.context.workflowId, "t");
    mid = store.get(wf.context.workflowId, "t");
    expect(mid.replanHistory ?? []).toEqual([]);  // STILL no entry

    // 3rd runNext → throw → maxRetries exhausted → REPLAN → ONE entry.
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    expect(after.replanHistory!.length).toBe(1);
    expect(after.replanHistory![0].errorName).toBe("RetryableError");
    // retryable: true — the underlying error WAS retryable; the
    // replan only triggered because the budget was exhausted, not
    // because the error was permanent.
    expect(after.replanHistory![0].retryable).toBe(true);
  });
});
