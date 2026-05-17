import { randomUUID } from "crypto";
import { WorkflowContext, WorkflowState, WorkflowStep } from "./types";

export class WorkflowPlanner {
  createPlan(context: WorkflowContext, userGoal: string): WorkflowState {
    const steps: WorkflowStep[] = [
      {
        stepId: randomUUID(),
        name: "understand_goal",
        goal: "Analyze the user request and identify outcome",
        requiresApproval: false,
        status: "pending",
      },
      {
        stepId: randomUUID(),
        name: "select_tools",
        goal: "Identify tools required to complete task",
        requiresApproval: false,
        status: "pending",
      },
      {
        stepId: randomUUID(),
        name: "execute_task",
        goal: userGoal,
        requiredTool: "tool_dispatcher",
        requiresApproval: false,
        status: "pending",
      },
      {
        stepId: randomUUID(),
        name: "quality_review",
        goal: "Validate output quality, safety, and traceability",
        requiredTool: "quality_scorer",
        requiresApproval: false,
        status: "pending",
      },
    ];

    const now = new Date().toISOString();

    return {
      context,
      status: "created",
      userGoal,
      steps,
      currentStepIndex: 0,
      createdAt: now,
      updatedAt: now,
    };
  }
}
