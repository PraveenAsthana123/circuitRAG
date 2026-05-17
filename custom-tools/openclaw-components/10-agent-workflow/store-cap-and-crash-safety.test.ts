// Negative drills for Iteration 7 (2026-05-17):
//   - WorkflowStateStore history cap (P1)
//   - AgentWorkflowEngine crash-safe `running` save (P1)

import { describe, it, expect } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowState } from "./types";

function newState(workflowId: string): WorkflowState {
  return {
    context: {
      workflowId,
      requestId: "r",
      tenantId: "t",
      userId: "u",
      traceId: "tr",
    },
    status: "created",
    userGoal: "g",
    steps: [],
    currentStepIndex: 0,
    createdAt: "2026-05-17T00:00:00.000Z",
    updatedAt: "2026-05-17T00:00:00.000Z",
  };
}

describe("WorkflowStateStore — history cap (P1)", () => {
  it("history does not exceed maxHistoryPerWorkflow", () => {
    const store = new WorkflowStateStore(3);
    const wfId = "wf-cap";

    // First save: no prior, no history entry.
    store.save(newState(wfId));
    expect(store.historyDepth(wfId)).toBe(0);

    // 10 subsequent saves; cap is 3, so depth should plateau at 3.
    for (let i = 0; i < 10; i++) {
      store.save(newState(wfId));
    }
    expect(store.historyDepth(wfId)).toBe(3);
  });

  it("rejects maxHistoryPerWorkflow < 1", () => {
    expect(() => new WorkflowStateStore(0)).toThrow();
    expect(() => new WorkflowStateStore(-5)).toThrow();
  });

  it("default cap is 50", () => {
    const store = new WorkflowStateStore();
    const wfId = "wf-default";
    store.save(newState(wfId));
    for (let i = 0; i < 200; i++) store.save(newState(wfId));
    expect(store.historyDepth(wfId)).toBe(50);
  });
});

describe("AgentWorkflowEngine — crash-safe step transitions (P1)", () => {
  it("REGRESSION: step status is persisted to 'running' BEFORE await", async () => {
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(),
      new Replanner(),
      new ToolSelector(),
      new HumanApprovalGate(),
      store,
    );

    const wf = engine.start(
      {
        workflowId: "wf-crash",
        requestId: "r", tenantId: "t", userId: "u", traceId: "tr",
      },
      "test crash safety",
    );

    // Spy on the store: track step 0's status at each save. Pre-fix:
    // "running" was mutated but never persisted, so the only status
    // ever saved for step 0 was "completed".
    const step0Statuses: string[] = [];
    const originalSave = store.save.bind(store);
    store.save = (s) => {
      const step0 = s.steps[0];
      if (step0) step0Statuses.push(step0.status);
      originalSave(s);
    };

    await engine.runNext(wf.context.workflowId, "t");

    // BACKDOOR CHECK (pre-fix): no "running" would appear because
    // status mutation happened but no save() was called between
    // mutating to "running" and mutating to "completed".
    expect(step0Statuses).toContain("running");
    expect(step0Statuses).toContain("completed");
    const runIdx = step0Statuses.indexOf("running");
    const compIdx = step0Statuses.indexOf("completed");
    expect(runIdx).toBeGreaterThanOrEqual(0);
    expect(compIdx).toBeGreaterThan(runIdx);
  });
});
