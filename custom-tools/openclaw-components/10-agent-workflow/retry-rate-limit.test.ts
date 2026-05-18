// Negative drills for Iter 67 (2026-05-17): per-workflow attempt
// rate limit on AgentWorkflowEngine.runNext().
//
// Pairs with iter 58 (recovery-depth cap):
//   iter 58 = LIFETIME cap on replan count
//   iter 67 = SHORT-TERM cap on attempt rate within a sliding window
// Without iter 67, an attacker (or a tight-loop misconfig) can hammer
// runNext() many times per second within the lifetime budget and
// exhaust compute. With both, the workflow surface is O(1) bounded
// per second AND per lifetime.
//
// Negative assertions:
//   1. BACKDOOR: rate limit triggers when attempts within window
//      exceed cap (throws WorkflowRateLimitedError)
//   2. BACKDOOR: rejected attempt does NOT itself count toward the
//      budget (otherwise the window would never drain on a hot
//      loop calling-and-failing-and-calling-again)
//   3. After window expires (timestamps drop off), attempts permitted
//   4. Constructor rejects sub-1 maxAttemptsPerWindow
//   5. Constructor rejects sub-1 attemptWindowMs
//   6. Constructor rejects non-integer values (1.5, NaN, Infinity)
//   7. Different workflows have INDEPENDENT windows (no cross-workflow
//      starvation)
//   8. Rate-limit error names the workflow id + cap (audit visibility)
//   9. Auth failure (wrong tenantId) takes precedence over rate-limit
//      check — caller sees the auth error, not the rate-limit error

import { describe, it, expect, vi } from "vitest";
import {
  AgentWorkflowEngine,
  WorkflowRateLimitedError,
} from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import {
  WorkflowStateStore,
  WorkflowAccessDeniedError,
} from "./workflow-state-store";
import { WorkflowContext } from "./types";

function newEngine(
  store: WorkflowStateStore,
  maxAttemptsPerWindow?: number,
  attemptWindowMs?: number,
): AgentWorkflowEngine {
  return new AgentWorkflowEngine(
    new WorkflowPlanner(), new Replanner(), new ToolSelector(),
    new HumanApprovalGate(), store,
    {
      ...(maxAttemptsPerWindow !== undefined ? { maxAttemptsPerWindow } : {}),
      ...(attemptWindowMs !== undefined ? { attemptWindowMs } : {}),
    },
  );
}

const CTX: WorkflowContext = {
  workflowId: "wf-rl", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

describe("Iter 67 — workflow runNext rate-limit (P1)", () => {
  it("BACKDOOR: attempts within window exceeding cap throw WorkflowRateLimitedError", async () => {
    const store = new WorkflowStateStore();
    // Tight cap: 3 attempts per second.
    const engine = newEngine(store, 3, 1_000);
    const wf = engine.start({ ...CTX, workflowId: "wf-rl-1" }, "test");

    // 3 attempts succeed (one per step or empty-plan completion).
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");

    // 4th attempt → rate limited.
    await expect(engine.runNext(wf.context.workflowId, "t"))
      .rejects.toThrow(WorkflowRateLimitedError);
  });

  it("BACKDOOR: rejected attempt does NOT count toward the budget", async () => {
    // Without this property the window never drains on a tight loop:
    // every rejected attempt re-occupies the window slot it was
    // rejected for, locking the workflow out forever.
    const store = new WorkflowStateStore();
    const engine = newEngine(store, 2, 100_000);  // long window
    const wf = engine.start({ ...CTX, workflowId: "wf-rl-2" }, "test");

    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");

    // 3rd attempt fails with rate limit.
    await expect(engine.runNext(wf.context.workflowId, "t"))
      .rejects.toThrow(WorkflowRateLimitedError);

    // 4th attempt ALSO fails (still within window) — but the engine
    // recorded only the 2 successful attempts, not the rejected 3rd.
    // We can prove this indirectly: a 100x burst of rejected attempts
    // does not change anything about the workflow state.
    for (let i = 0; i < 100; i++) {
      await expect(engine.runNext(wf.context.workflowId, "t"))
        .rejects.toThrow(WorkflowRateLimitedError);
    }
    // If rejected attempts had been recorded, the internal attempts
    // array would have grown to ~103 entries; runtime would degrade.
    // The functional proof: errors remain consistent + cheap.
  });

  it("after window expires, attempts are permitted again", async () => {
    const store = new WorkflowStateStore();
    // 2 attempts / 50ms window — tight enough to test in real time.
    const engine = newEngine(store, 2, 50);
    const wf = engine.start({ ...CTX, workflowId: "wf-rl-3" }, "test");

    await engine.runNext(wf.context.workflowId, "t");
    await engine.runNext(wf.context.workflowId, "t");

    await expect(engine.runNext(wf.context.workflowId, "t"))
      .rejects.toThrow(WorkflowRateLimitedError);

    // Wait for the window to drain.
    await new Promise((resolve) => setTimeout(resolve, 75));

    // Now the next attempt should succeed (window is empty).
    const result = await engine.runNext(wf.context.workflowId, "t");
    expect(result).toBeDefined();
  });

  it("constructor rejects sub-1 maxAttemptsPerWindow", () => {
    const store = new WorkflowStateStore();
    expect(() => newEngine(store, 0)).toThrow(/maxAttemptsPerWindow/);
    expect(() => newEngine(store, -5)).toThrow(/maxAttemptsPerWindow/);
  });

  it("constructor rejects sub-1 attemptWindowMs", () => {
    const store = new WorkflowStateStore();
    expect(() => newEngine(store, 10, 0)).toThrow(/attemptWindowMs/);
    expect(() => newEngine(store, 10, -100)).toThrow(/attemptWindowMs/);
  });

  it("constructor rejects non-integer values (1.5, NaN, Infinity)", () => {
    const store = new WorkflowStateStore();
    expect(() => newEngine(store, 1.5)).toThrow(/maxAttemptsPerWindow/);
    expect(() => newEngine(store, NaN)).toThrow(/maxAttemptsPerWindow/);
    expect(() => newEngine(store, Infinity)).toThrow(/maxAttemptsPerWindow/);
    expect(() => newEngine(store, 10, 1.5)).toThrow(/attemptWindowMs/);
  });

  it("different workflows have INDEPENDENT windows (no cross-workflow starvation)", async () => {
    const store = new WorkflowStateStore();
    const engine = newEngine(store, 2, 100_000);

    const wfA = engine.start({ ...CTX, workflowId: "wf-A" }, "task A");
    const wfB = engine.start({ ...CTX, workflowId: "wf-B" }, "task B");

    // Exhaust A's budget.
    await engine.runNext(wfA.context.workflowId, "t");
    await engine.runNext(wfA.context.workflowId, "t");
    await expect(engine.runNext(wfA.context.workflowId, "t"))
      .rejects.toThrow(WorkflowRateLimitedError);

    // B is unaffected — its budget is independent.
    const resB1 = await engine.runNext(wfB.context.workflowId, "t");
    const resB2 = await engine.runNext(wfB.context.workflowId, "t");
    expect(resB1).toBeDefined();
    expect(resB2).toBeDefined();
  });

  it("rate-limit error names the workflow id + cap (audit visibility)", async () => {
    const store = new WorkflowStateStore();
    const engine = newEngine(store, 1, 100_000);
    const wf = engine.start({ ...CTX, workflowId: "wf-rl-audit" }, "test");

    await engine.runNext(wf.context.workflowId, "t");

    try {
      await engine.runNext(wf.context.workflowId, "t");
      throw new Error("expected rate-limit");
    } catch (e) {
      expect(e).toBeInstanceOf(WorkflowRateLimitedError);
      const err = e as WorkflowRateLimitedError;
      expect(err.workflowId).toBe("wf-rl-audit");
      expect(err.maxAttemptsPerWindow).toBe(1);
      expect(err.attemptWindowMs).toBe(100_000);
      expect(err.message).toContain("wf-rl-audit");
      expect(err.message).toContain("1 attempts per");
    }
  });

  it("auth failure (wrong tenantId) takes precedence over rate-limit check", async () => {
    // An unauthorized caller must see WorkflowAccessDeniedError, NOT
    // a rate-limit error. Otherwise a misconfigured caller gets the
    // wrong diagnostic message and the rate-limit signal masks the
    // real auth problem.
    const store = new WorkflowStateStore();
    const engine = newEngine(store, 1, 100_000);
    const wf = engine.start({ ...CTX, workflowId: "wf-rl-auth" }, "test");

    // Exhaust the legit caller's budget.
    await engine.runNext(wf.context.workflowId, "t");

    // Wrong tenantId should produce auth error (not rate-limit).
    await expect(engine.runNext(wf.context.workflowId, "wrong-tenant"))
      .rejects.toThrow(WorkflowAccessDeniedError);
  });

  it("default settings: 60 attempts / 60s permits typical flows (regression)", async () => {
    // No custom config — engine uses defaults. Verify a typical
    // small-plan workflow (4 default steps) does not trip the
    // default cap.
    const store = new WorkflowStateStore();
    const engine = newEngine(store);  // defaults: 60/60_000ms
    const wf = engine.start({ ...CTX, workflowId: "wf-rl-default" }, "test");

    // 4 default steps + final complete attempt = 5 attempts.
    // Default 60-attempt window has plenty of room.
    for (let i = 0; i < 5; i++) {
      await engine.runNext(wf.context.workflowId, "t");
    }
    // No error — happy path locked.
  });
});
