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
  /** Iter 57 (2026-05-17): last error envelope from this step's most
   *  recent failed attempt. Set on every retry AND on the
   *  permanent-failure path so the audit row + downstream replan can
   *  see what went wrong. Cleared to undefined when the step
   *  eventually succeeds, so a leftover error from an earlier retry
   *  cannot be misread as the cause of the final state. */
  lastError?: StepErrorEnvelope;
}

/**
 * Iter 57 (2026-05-17): structured error info captured when a step
 * throws. Distinct from the raw Error object because:
 *   - Persisted across structuredClone (Error instances would
 *     lose their prototype chain).
 *   - Carries `retryable: boolean` so an audit consumer doesn't have
 *     to re-parse `name === "RetryableError"`.
 *   - Stack is optional — some platforms / production builds strip
 *     stack info, and we don't want the engine to crash on absence.
 */
export interface StepErrorEnvelope {
  /** Error class name, e.g. "RetryableError" or "TypeError". */
  name: string;
  /** Human-readable error message. NEVER include secrets here —
   *  the engine does not redact. The tool implementation is
   *  responsible for not embedding sensitive values in error
   *  messages. */
  message: string;
  /** JS engine stack trace if available. Optional. */
  stack?: string;
  /** True if the error was a RetryableError (transient class).
   *  False for any other thrown value. */
  retryable: boolean;
  /** ISO-8601 timestamp the engine captured the error. */
  timestamp: string;
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
