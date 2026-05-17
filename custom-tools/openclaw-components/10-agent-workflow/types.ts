export type WorkflowStatus =
  | "created"
  | "planning"
  | "awaiting_approval"
  | "executing"
  | "replanning"
  | "completed"
  | "failed"
  | "rolled_back";

export interface WorkflowContext {
  workflowId: string;
  requestId: string;
  tenantId: string;
  userId: string;
  traceId: string;
}

export interface WorkflowStep {
  stepId: string;
  name: string;
  goal: string;
  requiredTool?: string;
  requiresApproval: boolean;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
}

export interface WorkflowState {
  context: WorkflowContext;
  status: WorkflowStatus;
  userGoal: string;
  steps: WorkflowStep[];
  currentStepIndex: number;
  createdAt: string;
  updatedAt: string;
}
