import { randomUUID } from "crypto";
import { WorkflowState, WorkflowStep } from "./types";

export class Replanner {
  replan(state: WorkflowState, failureReason: string): WorkflowState {
    const recoveryStep: WorkflowStep = {
      stepId: randomUUID(),
      name: "recovery_step",
      goal: `Recover from failure: ${failureReason}`,
      requiredTool: "fallback_handler",
      requiresApproval: false,
      status: "pending" as const,
    };

    const prefix = state.steps.slice(0, state.currentStepIndex);
    const failedStep = state.steps[state.currentStepIndex];
    const suffix = state.steps.slice(state.currentStepIndex + 1);
    const preservedFailedStep: WorkflowStep[] = failedStep
      ? [{ ...failedStep, status: "failed" }]
      : [];

    return {
      ...state,
      status: "replanning",
      steps: [...prefix, ...preservedFailedStep, recoveryStep, ...suffix],
      currentStepIndex: prefix.length + preservedFailedStep.length,
    };
  }
}
