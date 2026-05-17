import { WorkflowContext, WorkflowStep } from "./types";

export class HumanApprovalGate {
  requestApproval(context: WorkflowContext, step: WorkflowStep): string {
    const approvalId = crypto.randomUUID();

    console.log(JSON.stringify({
      type: "human_approval_required",
      approvalId,
      workflowId: context.workflowId,
      requestId: context.requestId,
      tenantId: context.tenantId,
      stepId: step.stepId,
      stepName: step.name,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    }));

    return approvalId;
  }
}
