import { WorkflowStep } from "./types";

export class ToolSelector {
  select(step: WorkflowStep): string {
    if (step.requiredTool) return step.requiredTool;

    if (step.name.includes("quality")) return "quality_scorer";
    if (step.name.includes("approval")) return "human_approval";

    return "default_agent_executor";
  }
}
