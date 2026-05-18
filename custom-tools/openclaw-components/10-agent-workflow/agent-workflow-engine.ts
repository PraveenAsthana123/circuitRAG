import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RollbackManager } from "./rollback-manager";
import {
  WorkflowContext,
  WorkflowState,
  WorkflowStep,
  RetryableError,
  StepErrorEnvelope,
} from "./types";

const cloneSteps = (steps: WorkflowStep[]): WorkflowStep[] =>
  steps.map((step) => ({ ...step }));

/**
 * Iter 59 (2026-05-17): redact absolute filesystem paths from a JS
 * stack trace while preserving function names and `:line:col`.
 *
 * Examples:
 *   "    at fn (/mnt/deepa/rag/.../engine.ts:42:10)"
 *     → "    at fn ([redacted]:42:10)"
 *   "    at fn (file:///home/p/proj/file.mjs:7:3)"
 *     → "    at fn ([redacted]:7:3)"
 *   "    at /tmp/x.mjs:5:9"             (anonymous, no parens)
 *     → "    at [redacted]:5:9"
 *   "    at runScriptInThisContext (node:internal/vm:209:10)"
 *     → unchanged (node:internal/* carries no host info)
 *
 * Exported for the iter 59 drill — not part of the public engine API.
 */
export function redactStackPaths(stack: string | undefined): string | undefined {
  if (stack === undefined) return undefined;
  return stack.split("\n").map((line) => {
    // node:internal pseudo-URLs reveal no host info — leave alone.
    if (line.includes("(node:") || /\bat\s+node:/.test(line)) return line;
    // Parenthesized form: "    at fn ((file:///)?/path/to/file.ts:LINE:COL)"
    // Capture trailing :digits:digits and replace the path inside parens.
    let redacted = line.replace(
      /\(((?:file:\/\/\/?)?[^()]+?)(:\d+:\d+)\)/g,
      "([redacted]$2)",
    );
    // Anonymous form: "    at /path/to/file.ts:LINE:COL"  (no parens)
    redacted = redacted.replace(
      /(\s+at\s+)((?:file:\/\/\/?)?(?:\/|[A-Za-z]:[\\/])[^\s()]+?)(:\d+:\d+)\s*$/,
      "$1[redacted]$3",
    );
    return redacted;
  }).join("\n");
}

const DEFAULT_MAX_STEP_OUTPUT_BYTES = 64 * 1024;
/** Iter 58: cap how many recovery_steps replan may insert per
 *  workflow. Without a cap, a recovery_step that itself fails will
 *  trigger ANOTHER recovery_step; the step list grows unboundedly
 *  and the workflow-state-store memory does too. Default 3 allows
 *  modest in-flight recovery (try → recovery → recovery → recovery)
 *  before declaring the workflow lost. */
const DEFAULT_MAX_RECOVERY_DEPTH = 3;
/** Iter 58: canonical name a replanned step gets. The replanner
 *  also uses this string; the engine counts steps with this name to
 *  enforce the cap. If you rename it in replanner.ts, update here. */
const RECOVERY_STEP_NAME = "recovery_step";

export interface AgentWorkflowEngineOptions {
  /** Iter 56: cap persisted per-step output to defend in-memory state. */
  maxStepOutputBytes?: number;
  /** Iter 58: cap recovery-step replan depth per workflow. When the
   *  workflow already contains this many recovery_steps and another
   *  failure occurs, the engine does NOT replan again — it marks the
   *  workflow `failed` and stops. */
  maxRecoveryDepth?: number;
  /** Iter 59: redact host filesystem paths from lastError.stack
   *  before persisting. Default `true` because audit rows + operator
   *  UIs surface this field; leaking absolute paths reveals deploy
   *  layout to anyone reading the workflow. Set `false` in dev to
   *  preserve full debuggable stacks. Function names, line, and
   *  column are always preserved. */
  redactStackPaths?: boolean;
}

export class StepOutputTooLargeError extends Error {
  constructor(sizeBytes: number, maxBytes: number) {
    super(`Step output is ${sizeBytes} bytes; limit is ${maxBytes} bytes`);
    this.name = "StepOutputTooLargeError";
  }
}

/** Iter 58: raised internally when the recovery cap is hit. Surfaces
 *  on the failed step's lastError so operator can see "we gave up
 *  retrying recovery" rather than just "workflow failed". */
export class RecoveryDepthExceededError extends Error {
  constructor(depth: number, max: number) {
    super(`Recovery depth ${depth} exceeds max ${max}; workflow abandoned`);
    this.name = "RecoveryDepthExceededError";
  }
}

/**
 * Iter 55 (2026-05-17): read-only view of prior completed steps'
 * outputs, passed into simulateToolExecution so a step can chain
 * off upstream results (e.g. fetch-then-summarize). Stale outputs
 * from retried/replanned steps are excluded — only `completed`
 * steps before currentStepIndex appear.
 */
export interface StepOutputContext {
  /** Output of an upstream completed step, by name. undefined if no
   *  such step has completed yet. */
  getByName(stepName: string): unknown;
  /** Output of an upstream completed step, by stepId. undefined if
   *  no such step has completed yet. */
  getById(stepId: string): unknown;
}

export class AgentWorkflowEngine {
  private readonly rollbackManager: RollbackManager;

  constructor(
    private readonly planner: WorkflowPlanner,
    private readonly replanner: Replanner,
    private readonly toolSelector: ToolSelector,
    private readonly approvalGate: HumanApprovalGate,
    private readonly store: WorkflowStateStore,
    private readonly options: AgentWorkflowEngineOptions = {},
  ) {
    this.rollbackManager = new RollbackManager(store);
    const maxBytes = this.maxStepOutputBytes();
    if (!Number.isFinite(maxBytes) || maxBytes < 0) {
      throw new Error("maxStepOutputBytes must be a non-negative finite number");
    }
    const maxDepth = this.maxRecoveryDepth();
    if (!Number.isInteger(maxDepth) || maxDepth < 0) {
      throw new Error("maxRecoveryDepth must be a non-negative integer");
    }
  }

  start(context: WorkflowContext, userGoal: string): WorkflowState {
    const state = this.planner.createPlan(context, userGoal);

    this.store.save({
      ...state,
      status: "planning",
    });

    console.log(JSON.stringify({
      type: "workflow_started",
      workflowId: context.workflowId,
      requestId: context.requestId,
      tenantId: context.tenantId,
      stepCount: state.steps.length,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    }));

    return state;
  }

  async runNext(workflowId: string, callerTenantId: string): Promise<WorkflowState> {
    // tenantId required for §47 multi-tenant isolation; the store
    // throws WorkflowAccessDeniedError if it doesn't match.
    const state = this.store.get(workflowId, callerTenantId);
    const step = state.steps[state.currentStepIndex];

    if (!step) {
      const completed = {
        ...state,
        steps: cloneSteps(state.steps),
        status: "completed" as const,
      };
      this.store.save(completed);
      return completed;
    }

    if (step.requiresApproval) {
      this.approvalGate.requestApproval(state.context, step);

      const waiting = {
        ...state,
        steps: cloneSteps(state.steps),
        status: "awaiting_approval" as const,
      };

      this.store.save(waiting);
      return waiting;
    }

    const toolName = this.toolSelector.select(step);

    // Iter 55: build the read-only output context for THIS step.
    // Only completed upstream steps contribute; retried steps with
    // status reset to "pending" automatically vanish from the lookup.
    const outputContext = this.buildOutputContext(state.steps, state.currentStepIndex);

    try {
      console.log(JSON.stringify({
        type: "workflow_step_started",
        workflowId,
        stepId: step.stepId,
        stepName: step.name,
        selectedTool: toolName,
        traceId: state.context.traceId,
        timestamp: new Date().toISOString(),
      }));

      // ✅ P1 FIXED (2026-05-17): persist `running` BEFORE awaiting
      // the tool. Pre-fix: status was mutated but not saved; a crash
      // mid-tool left the step looking `pending` on restart and it
      // would run twice. Now the running state is durable.
      step.status = "running";
      this.store.save({
        ...state,
        steps: cloneSteps(state.steps),
        status: "executing" as const,
      });

      const result = await this.simulateToolExecution(toolName, outputContext, step);
      const outputSizeBytes = this.measureOutputBytes(result);
      if (outputSizeBytes > this.maxStepOutputBytes()) {
        throw new StepOutputTooLargeError(outputSizeBytes, this.maxStepOutputBytes());
      }

      step.status = "completed";
      // Iter 55: persist the tool's return value so a downstream
      // step's outputContext.getByName(step.name) can read it.
      // Iter 56: output was measured before assignment, so oversized
      // values fail the step before they enter persisted workflow state.
      step.output = result;
      step.outputSizeBytes = outputSizeBytes;
      // Iter 57: success path clears any stale error from a prior
      // retried attempt — the final state of the step is "completed
      // with no error", not "completed with a leftover error".
      step.lastError = undefined;

      const nextState = {
        ...state,
        steps: cloneSteps(state.steps),
        status: "executing" as const,
        currentStepIndex: state.currentStepIndex + 1,
      };

      this.store.save(nextState);

      return nextState;
    } catch (error) {
      // Iter 44: distinguish transient (retryable) from permanent.
      const isRetryable = error instanceof RetryableError;
      const currentRetries = step.retryCount ?? 0;
      const maxRetries = step.maxRetries ?? 0;

      if (isRetryable && currentRetries < maxRetries) {
        step.retryCount = currentRetries + 1;
        step.status = "pending"; // ready for the next runNext() call
        // Iter 55: a retried step has no valid output yet — clear any
        // stale value so the rerun's outputContext cannot read a
        // failed-and-retried sibling's leftover data.
        step.output = undefined;
        step.outputSizeBytes = undefined;
        // Iter 57: capture the error envelope so audit / debugging /
        // operator UI can see WHY the retry happened. Overwritten on
        // every retry attempt, cleared on success, preserved through
        // replan on the permanent path.
        step.lastError = this.toErrorEnvelope(error, true);
        const retryState = {
          ...state,
          steps: cloneSteps(state.steps),
          status: "executing" as const,
        };
        this.store.save(retryState);

        console.warn(JSON.stringify({
          type: "workflow_step_retry",
          workflowId,
          stepId: step.stepId,
          retryCount: step.retryCount,
          maxRetries,
          error: error.message,
          traceId: state.context.traceId,
          timestamp: new Date().toISOString(),
        }));

        return retryState;
      }

      // Non-retryable OR exhausted → replan.
      step.status = "failed";
      // Iter 55: a failed step has no valid output.
      step.output = undefined;
      step.outputSizeBytes = undefined;
      // Iter 57: attach error envelope BEFORE replan so the
      // replanner's `{...failedStep, status: "failed"}` copy carries
      // it through to the final state. Operator UI sees lastError
      // on the failed step even after the recovery step has run.
      step.lastError = this.toErrorEnvelope(error, isRetryable);

      // Iter 58: cap recovery depth. Count recovery_steps in the
      // CURRENT plan; if at/above cap, abandon the workflow rather
      // than inserting yet another doomed recovery_step. The just-
      // failed step's lastError is overwritten with a
      // RecoveryDepthExceededError so the audit row makes the
      // STOP-REASON visible (not just "permanent fail").
      const existingRecoveryCount = state.steps.filter(
        (s) => s.name === RECOVERY_STEP_NAME,
      ).length;
      if (existingRecoveryCount >= this.maxRecoveryDepth()) {
        const giveUp = new RecoveryDepthExceededError(
          existingRecoveryCount,
          this.maxRecoveryDepth(),
        );
        step.lastError = this.toErrorEnvelope(giveUp, false);
        const abandoned = {
          ...state,
          steps: cloneSteps(state.steps),
          status: "failed" as const,
        };
        this.store.save(abandoned);
        console.warn(JSON.stringify({
          type: "workflow_abandoned",
          workflowId,
          stepId: step.stepId,
          recoveryDepth: existingRecoveryCount,
          maxRecoveryDepth: this.maxRecoveryDepth(),
          reason: giveUp.message,
          traceId: state.context.traceId,
          timestamp: new Date().toISOString(),
        }));
        return abandoned;
      }

      const replanned = this.replanner.replan(
        {
          ...state,
          steps: cloneSteps(state.steps),
          status: "failed",
        },
        error instanceof Error ? error.message : "Unknown error"
      );

      this.store.save(replanned);

      return replanned;
    }
  }

  rollback(workflowId: string, callerTenantId: string, reason: string): WorkflowState {
    // tenantId required for §47 multi-tenant isolation.
    return this.rollbackManager.rollback(workflowId, callerTenantId, reason);
  }

  // Protected so a test subclass can override to simulate retryable
  // vs permanent failures. Real production replaces this entirely
  // with a Component 3 ToolDispatcher.dispatch() call.
  //
  // Iter 55: now returns the tool's result (unknown). The engine
  // persists it on the step so downstream steps can read it via
  // the StepOutputContext passed in `context`. The default impl
  // returns undefined to preserve pre-iter-55 behavior.
  protected async simulateToolExecution(
    toolName: string,
    _context: StepOutputContext,
    _step: WorkflowStep,
  ): Promise<unknown> {
    if (!toolName) {
      throw new Error("No tool selected");
    }
    return undefined;
  }

  private maxStepOutputBytes(): number {
    return this.options.maxStepOutputBytes ?? DEFAULT_MAX_STEP_OUTPUT_BYTES;
  }

  private maxRecoveryDepth(): number {
    return this.options.maxRecoveryDepth ?? DEFAULT_MAX_RECOVERY_DEPTH;
  }

  // Iter 57: normalize anything thrown into the persisted error
  // envelope. Non-Error throws ("string", numbers, undefined) are
  // common in JS — the catch block must NOT crash when stack/message
  // are absent.
  // Iter 59: stack is redacted by default to hide host filesystem
  // layout from anyone who can read the persisted envelope.
  private toErrorEnvelope(thrown: unknown, retryable: boolean): StepErrorEnvelope {
    const now = new Date().toISOString();
    if (thrown instanceof Error) {
      return {
        name: thrown.name,
        message: thrown.message,
        stack: this.shouldRedactStack() ? redactStackPaths(thrown.stack) : thrown.stack,
        retryable,
        timestamp: now,
      };
    }
    return {
      name: "NonError",
      message: typeof thrown === "string" ? thrown : JSON.stringify(thrown ?? null),
      retryable,
      timestamp: now,
    };
  }

  private shouldRedactStack(): boolean {
    return this.options.redactStackPaths ?? true;
  }

  private measureOutputBytes(output: unknown): number {
    if (output === undefined) return 0;

    let serialized: string;
    try {
      serialized = JSON.stringify(output);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      throw new Error(`Step output must be JSON-serializable: ${message}`);
    }

    if (serialized === undefined) return 0;
    return Buffer.byteLength(serialized, "utf8");
  }

  // Iter 55: build the read-only output view passed to a tool. Only
  // steps strictly before `currentStepIndex` with status === "completed"
  // contribute — pending / running / failed / skipped steps are
  // invisible, and a step cannot see its own output (lookup is
  // by upstream completed steps only).
  private buildOutputContext(
    steps: WorkflowStep[],
    currentStepIndex: number,
  ): StepOutputContext {
    const upstream = steps.slice(0, currentStepIndex).filter(
      (s) => s.status === "completed",
    );
    return {
      getByName(stepName: string): unknown {
        const hit = upstream.find((s) => s.name === stepName);
        return hit ? hit.output : undefined;
      },
      getById(stepId: string): unknown {
        const hit = upstream.find((s) => s.stepId === stepId);
        return hit ? hit.output : undefined;
      },
    };
  }
}
