export interface AgentTask {
  sessionId: string;
  userId: string;
  userInput: string;
  /** Iter 48: required for downstream Component 3/8 calls. Optional
   *  on the type for backcompat with the original Component 1
   *  Gateway test, which constructed AgentTask without it. The
   *  Executor (when wired with a real ModelClient/ToolDispatcher)
   *  rejects steps that need it but lack it. */
  tenantId?: string;
  requestId?: string;
  traceId?: string;
  roles?: string[];
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
