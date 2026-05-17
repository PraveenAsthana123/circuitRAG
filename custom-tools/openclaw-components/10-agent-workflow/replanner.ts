import { WorkflowState } from "./types";

export class Replanner {
  replan(state: WorkflowState, failureReason: string): WorkflowState {
    const recoveryStep = {
      stepId: crypto.randomUUID(),
      name: "recovery_step",
      goal: `Recover from failure: ${failureReason}`,
      requiredTool: "fallback_handler",
      requiresApproval: false,
      status: "pending" as const,
    };

    return {
      ...state,
      status: "replanning",
      steps: [
        ...state.steps.slice(0, state.currentStepIndex + 1),
        recoveryStep,
        ...state.steps.slice(state.currentStepIndex + 1),
      ],
    };
  }
}
