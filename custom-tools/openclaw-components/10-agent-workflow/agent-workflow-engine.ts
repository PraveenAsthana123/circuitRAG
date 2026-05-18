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

const DEFAULT_MAX_STEP_OUTPUT_BYTES = 64 * 1024;

export interface AgentWorkflowEngineOptions {
  /** Iter 56: cap persisted per-step output to defend in-memory state. */
  maxStepOutputBytes?: number;
}

export class StepOutputTooLargeError extends Error {
  constructor(sizeBytes: number, maxBytes: number) {
    super(`Step output is ${sizeBytes} bytes; limit is ${maxBytes} bytes`);
    this.name = "StepOutputTooLargeError";
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

  // Iter 57: normalize anything thrown into the persisted error
  // envelope. Non-Error throws ("string", numbers, undefined) are
  // common in JS — the catch block must NOT crash when stack/message
  // are absent.
  private toErrorEnvelope(thrown: unknown, retryable: boolean): StepErrorEnvelope {
    const now = new Date().toISOString();
    if (thrown instanceof Error) {
      return {
        name: thrown.name,
        message: thrown.message,
        stack: thrown.stack,
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
