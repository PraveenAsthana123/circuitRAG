export interface AgentTask {
  sessionId: string;
  userId: string;
  userInput: string;
}

export interface PlanStep {
  stepId: string;
  action: "think" | "tool" | "respond";
  description: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
}

export interface AgentPlan {
  taskId: string;
  steps: PlanStep[];
}

export interface ExecutionResult {
  stepId: string;
  success: boolean;
  output: unknown;
  error?: string;
}
