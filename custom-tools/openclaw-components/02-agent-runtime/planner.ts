import { randomUUID } from "crypto";
import { AgentTask, AgentPlan } from "./types";

export class Planner {
  createPlan(task: AgentTask): AgentPlan {
    return {
      taskId: randomUUID(),
      steps: [
        {
          stepId: randomUUID(),
          action: "think",
          description: "Understand user intent and required outcome",
        },
        {
          stepId: randomUUID(),
          action: "respond",
          description: `Answer user request: ${task.userInput}`,
        },
      ],
    };
  }
}
