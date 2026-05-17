import { AgentPlan, ExecutionResult } from "./types";

export class Executor {
  async execute(plan: AgentPlan): Promise<ExecutionResult[]> {
    const results: ExecutionResult[] = [];

    for (const step of plan.steps) {
      try {
        results.push({
          stepId: step.stepId,
          success: true,
          output: `Executed: ${step.description}`,
        });
      } catch (error) {
        results.push({
          stepId: step.stepId,
          success: false,
          output: null,
          error: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }

    return results;
  }
}
