import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RollbackManager } from "./rollback-manager";
import { WorkflowContext, WorkflowState, RetryableError } from "./types";

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
      const completed = { ...state, status: "completed" as const };
      this.store.save(completed);
      return completed;
    }

    if (step.requiresApproval) {
      this.approvalGate.requestApproval(state.context, step);

      const waiting = {
        ...state,
        status: "awaiting_approval" as const,
      };

      this.store.save(waiting);
      return waiting;
    }

    const toolName = this.toolSelector.select(step);

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
        status: "executing" as const,
      });

      await this.simulateToolExecution(toolName);

      step.status = "completed";

      const nextState = {
        ...state,
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
        const retryState = {
          ...state,
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
      const replanned = this.replanner.replan(
        {
          ...state,
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
  protected async simulateToolExecution(toolName: string): Promise<void> {
    if (!toolName) {
      throw new Error("No tool selected");
    }
  }
}
