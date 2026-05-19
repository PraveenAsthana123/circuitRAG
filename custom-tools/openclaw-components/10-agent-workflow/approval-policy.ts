import { WorkflowStep } from "./types";

export type ApprovalPolicyDecision = "allow" | "request_approval" | "deny";

export interface ApprovalPolicyResult {
  decision: ApprovalPolicyDecision;
  reason: string;
}

export interface ApprovalPolicyOptions {
  autoAllowLowRisk?: boolean;
  denyPatterns?: RegExp[];
  approvalRequiredTools?: string[];
}

export class ApprovalPolicy {
  private readonly autoAllowLowRisk: boolean;
  private readonly denyPatterns: RegExp[];
  private readonly approvalRequiredTools: Set<string>;

  constructor(options: ApprovalPolicyOptions = {}) {
    this.autoAllowLowRisk = options.autoAllowLowRisk ?? true;
    this.denyPatterns = options.denyPatterns ?? [
      /delete\s+production/i,
      /disable\s+audit/i,
      /exfiltrate/i,
      /steal\s+password/i,
    ];
    this.approvalRequiredTools = new Set(options.approvalRequiredTools ?? [
      "human_approval",
      "external_write",
      "data_export",
      "production_deploy",
    ]);
  }

  evaluate(step: WorkflowStep): ApprovalPolicyResult {
    const text = `${step.name} ${step.goal} ${step.requiredTool ?? ""}`;
    if (this.denyPatterns.some((pattern) => pattern.test(text))) {
      return { decision: "deny", reason: "Step matches a deny policy pattern" };
    }
    if (step.requiresApproval || (step.requiredTool && this.approvalRequiredTools.has(step.requiredTool))) {
      return { decision: "request_approval", reason: "Step requires policy approval" };
    }
    if (this.autoAllowLowRisk) {
      return { decision: "allow", reason: "Low-risk step auto-allowed by policy" };
    }
    return { decision: "request_approval", reason: "Auto-allow disabled" };
  }
}
