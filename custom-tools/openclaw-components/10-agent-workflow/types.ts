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
  /** Iter 55 (2026-05-17): result of a successful tool execution.
   *  Downstream steps may reference upstream outputs through the
   *  StepOutputContext passed into simulateToolExecution. Cleared
   *  to undefined on retry so a stale value can't be re-read by a
   *  later attempt. Set ONLY when status === "completed".
   *
   *  Iter 56: the engine refuses to persist outputs larger than its
   *  maxStepOutputBytes setting, so this field cannot grow workflow
   *  state without bound. */
  output?: unknown;
  /** UTF-8 JSON byte size of output when it was accepted. */
  outputSizeBytes?: number;
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
