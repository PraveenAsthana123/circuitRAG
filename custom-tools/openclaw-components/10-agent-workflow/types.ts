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
  /** Optional session id used when dispatching Component 3 tools.
   *  Defaults to workflowId for backwards-compatible local workflows. */
  sessionId?: string;
  /** Optional caller roles used by ToolDispatcher authorization. */
  roles?: string[];
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
  /** Nested Error.cause chain, persisted so tool/backend root causes
   *  survive replanning instead of being flattened to the top-level
   *  message only. */
  cause?: StepErrorCauseEnvelope;
  /** True if the error was a RetryableError (transient class).
   *  False for any other thrown value. */
  retryable: boolean;
  /** ISO-8601 timestamp the engine captured the error. */
  timestamp: string;
}

export interface StepErrorCauseEnvelope {
  name: string;
  message: string;
  stack?: string;
  cause?: StepErrorCauseEnvelope;
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

/**
 * Iter 66 (2026-05-17): workflow-level audit row appended every time
 * the engine replans (i.e. on the non-retryable failure path AND
 * when the recovery-depth cap is exceeded). RETRY attempts do NOT
 * append an entry — only true replans count toward the history.
 *
 * Persisted ON THE WORKFLOW STATE (not on individual steps) because
 * the question this answers is workflow-level: "how many times did
 * this workflow replan, and why?" Operator looking at a failed
 * workflow should be able to read the whole replan story without
 * walking every step's lastError.
 *
 * Survives structuredClone (only plain JSON-serializable fields).
 */
export interface ReplanHistoryEntry {
  /** ISO-8601 timestamp when the engine recorded the replan. */
  timestamp: string;
  /** stepId of the step whose failure caused the replan. */
  failedStepId: string;
  /** Human-readable step name (e.g. "execute_task" or
   *  "recovery_step") so the operator does not have to chase
   *  stepIds to recognize the row. */
  failedStepName: string;
  /** Error class name from the captured envelope (e.g.
   *  "RetryableError", "Error", "TypeError",
   *  "RecoveryDepthExceededError" on the abandon path). */
  errorName: string;
  /** Error message from the captured envelope. Sanitized by the
   *  same redaction policy that protects lastError.message. */
  errorMessage: string;
  /** True iff the underlying error was a RetryableError.
   *  Always false on the abandon path (RecoveryDepthExceededError
   *  is non-retryable by construction). */
  retryable: boolean;
  /** How many recovery_steps were in the plan AT THE TIME this
   *  entry was added. 0 on the first replan, grows as recovery_steps
   *  accumulate. On the abandon path this is the depth that
   *  TRIGGERED the abandon (already at the cap). */
  recoveryDepthAtTime: number;
}

export interface WorkflowState {
  context: WorkflowContext;
  status: WorkflowStatus;
  userGoal: string;
  steps: WorkflowStep[];
  currentStepIndex: number;
  createdAt: string;
  updatedAt: string;
  /** Iter 66 (2026-05-17): chronological list of replan events for
   *  this workflow. Undefined / empty on freshly-planned workflows
   *  and on workflows that completed without ever replanning. */
  replanHistory?: ReplanHistoryEntry[];
}
