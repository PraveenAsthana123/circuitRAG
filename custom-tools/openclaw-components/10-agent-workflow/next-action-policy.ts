import { ApprovalPolicy, ApprovalPolicyResult } from "./approval-policy";
import { WorkflowState } from "./types";

export type NextAction = "run_next" | "delegate_run_next" | "wait_for_approval" | "stop" | "deny";

export interface NextActionDecision {
  action: NextAction;
  reason: string;
  approval?: ApprovalPolicyResult;
}

export interface NextActionPolicyOptions {
  delegateByDefault?: boolean;
  approvalPolicy?: ApprovalPolicy;
}

export class NextActionPolicy {
  private readonly delegateByDefault: boolean;
  private readonly approvalPolicy: ApprovalPolicy;

  constructor(options: NextActionPolicyOptions = {}) {
    this.delegateByDefault = options.delegateByDefault ?? true;
    this.approvalPolicy = options.approvalPolicy ?? new ApprovalPolicy();
  }

  decide(state: WorkflowState): NextActionDecision {
    if (["completed", "failed", "rolled_back"].includes(state.status)) {
      return { action: "stop", reason: `Workflow is terminal: ${state.status}` };
    }
    if (state.status === "awaiting_approval") {
      return { action: "wait_for_approval", reason: "Workflow is already awaiting approval" };
    }

    const step = state.steps[state.currentStepIndex];
    if (!step) {
      return { action: "run_next", reason: "No current step; runNext will complete the workflow" };
    }

    const approval = this.approvalPolicy.evaluate(step);
    if (approval.decision === "deny") {
      return { action: "deny", reason: approval.reason, approval };
    }
    if (approval.decision === "request_approval") {
      return { action: "wait_for_approval", reason: approval.reason, approval };
    }

    return {
      action: this.delegateByDefault ? "delegate_run_next" : "run_next",
      reason: this.delegateByDefault ? "Policy delegates runnable work" : "Policy runs work inline",
      approval,
    };
  }
}
