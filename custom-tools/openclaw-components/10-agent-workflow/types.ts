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
  /** Iter 44 (2026-05-17): how many times this step has been retried. */
  retryCount?: number;
  /** Iter 44: max retries for this step before falling through to replan.
   *  Default 0 (no retry — preserves pre-fix behavior). */
  maxRetries?: number;
}

/**
 * Iter 44: errors caught by AgentWorkflowEngine.runNext check
 * `instanceof RetryableError`. Retryable errors (transient: network
 * blip, 5xx, timeout) cause a same-step retry up to maxRetries.
 * Non-RetryableError exceptions go straight to replan (permanent
 * failures: schema mismatch, policy denial).
 */
export class RetryableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RetryableError";
  }
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
