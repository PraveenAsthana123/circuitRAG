export type ModelProvider = "openai" | "anthropic" | "bedrock" | "ollama";
export type TaskType = "chat" | "code" | "rag" | "vision" | "reasoning";

export interface LLMRequest {
  requestId: string;
  tenantId: string;
  userId: string;
  taskType: TaskType;
  prompt: string;
  maxTokens: number;
  traceId: string;
}

export interface ModelConfig {
  modelId: string;
  provider: ModelProvider;
  supportedTasks: TaskType[];
  costPer1kTokensUsd: number;
  maxContextTokens: number;
  priority: number;
  enabled: boolean;
}

export interface LLMResponse {
  modelId: string;
  provider: ModelProvider;
  output: string;
  latencyMs: number;
  estimatedCostUsd: number;
  explanation: string;
  /** True if this response came from a fallback model after the
   *  primary failed (Iter 17). The primary model that was attempted
   *  is also included so observability can correlate the failure
   *  with the recovery. */
  fallbackUsed?: boolean;
  primaryAttempted?: string;
  primaryError?: string;
}
