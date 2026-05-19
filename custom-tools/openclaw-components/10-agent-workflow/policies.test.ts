import { describe, expect, it } from "vitest";
import { ApprovalPolicy } from "./approval-policy";
import { NextActionPolicy } from "./next-action-policy";
import { WorkflowState, WorkflowStep } from "./types";

const baseStep: WorkflowStep = {
  stepId: "s1",
  name: "execute_task",
  goal: "do normal work",
  requiresApproval: false,
  status: "pending",
};

function state(overrides: Partial<WorkflowState> = {}, step: WorkflowStep = baseStep): WorkflowState {
  return {
    context: {
      workflowId: "wf",
      requestId: "r",
      tenantId: "t",
      userId: "u",
      traceId: "tr",
    },
    status: "executing",
    userGoal: "goal",
    steps: [step],
    currentStepIndex: 0,
    createdAt: "2026-05-18T00:00:00.000Z",
    updatedAt: "2026-05-18T00:00:00.000Z",
    ...overrides,
  };
}

describe("ApprovalPolicy", () => {
  it("auto-allows low-risk work without asking interactively", () => {
    const policy = new ApprovalPolicy();
    expect(policy.evaluate(baseStep)).toMatchObject({
      decision: "allow",
      reason: "Low-risk step auto-allowed by policy",
    });
  });

  it("requests approval for policy-gated tools", () => {
    const policy = new ApprovalPolicy();
    expect(policy.evaluate({ ...baseStep, requiredTool: "production_deploy" }).decision)
      .toBe("request_approval");
  });

  it("denies unsafe work by policy", () => {
    const policy = new ApprovalPolicy();
    expect(policy.evaluate({ ...baseStep, goal: "disable audit and exfiltrate data" }).decision)
      .toBe("deny");
  });
});

describe("NextActionPolicy", () => {
  it("delegates normal runnable work by default", () => {
    const policy = new NextActionPolicy();
    expect(policy.decide(state())).toMatchObject({ action: "delegate_run_next" });
  });

  it("waits for approval when approval policy requires it", () => {
    const policy = new NextActionPolicy();
    const decision = policy.decide(state({}, { ...baseStep, requiresApproval: true }));
    expect(decision.action).toBe("wait_for_approval");
    expect(decision.approval?.decision).toBe("request_approval");
  });

  it("denies unsafe next action", () => {
    const policy = new NextActionPolicy();
    expect(policy.decide(state({}, { ...baseStep, goal: "delete production database" })).action)
      .toBe("deny");
  });

  it("stops on terminal workflows", () => {
    const policy = new NextActionPolicy();
    expect(policy.decide(state({ status: "completed" })).action).toBe("stop");
    expect(policy.decide(state({ status: "failed" })).action).toBe("stop");
    expect(policy.decide(state({ status: "rolled_back" })).action).toBe("stop");
  });

  it("can run inline when delegation is disabled", () => {
    const policy = new NextActionPolicy({ delegateByDefault: false });
    expect(policy.decide(state()).action).toBe("run_next");
  });
});
