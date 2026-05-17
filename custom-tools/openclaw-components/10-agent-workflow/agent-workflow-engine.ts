import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RollbackManager } from "./rollback-manager";
import { WorkflowContext, WorkflowState } from "./types";

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

  async runNext(workflowId: string): Promise<WorkflowState> {
    const state = this.store.get(workflowId);
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

      step.status = "running";

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

  rollback(workflowId: string, reason: string): WorkflowState {
    return this.rollbackManager.rollback(workflowId, reason);
  }

  private async simulateToolExecution(toolName: string): Promise<void> {
    if (!toolName) {
      throw new Error("No tool selected");
    }
  }
}
