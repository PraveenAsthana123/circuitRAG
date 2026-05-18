import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RollbackManager } from "./rollback-manager";
import { WorkflowContext, WorkflowState, WorkflowStep, RetryableError } from "./types";

const cloneSteps = (steps: WorkflowStep[]): WorkflowStep[] =>
  steps.map((step) => ({ ...step }));

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
    private readonly store: WorkflowStateStore
  ) {
    this.rollbackManager = new RollbackManager(store);
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

      step.status = "completed";
      // Iter 55: persist the tool's return value so a downstream
      // step's outputContext.getByName(step.name) can read it.
      step.output = result;

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
