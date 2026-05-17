import { AgentTask, AgentPlan } from "./types";

export class Planner {
  createPlan(task: AgentTask): AgentPlan {
    return {
      taskId: crypto.randomUUID(),
      steps: [
        {
          stepId: crypto.randomUUID(),
          action: "think",
          description: "Understand user intent and required outcome",
        },
        {
          stepId: crypto.randomUUID(),
          action: "respond",
          description: `Answer user request: ${task.userInput}`,
        },
      ],
    };
  }
}
