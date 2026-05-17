// ⚠️ STUB — this file was named in Component 2's folder layout but
//     NO source code was provided.
//
//     The Component 2 Executor's empty `try { ... } catch` block has
//     no statement that can throw — almost certainly because
//     `modelClient.complete(...)` was meant to live in that try body.
//     This stub delegates to Component 8's `LLMRouter` so the
//     executor has something real to call.
//
//     Replace with the operator's source if a different bridge was
//     intended. See ../NOTES.md (Component 2) + ../GAPS.md.

import { LLMRouter } from "../08-llm-router/llm-router";
import { LLMRequest, LLMResponse, TaskType } from "../08-llm-router/types";

export interface ModelCompleteInput {
  requestId: string;
  tenantId: string;
  userId: string;
  prompt: string;
  taskType?: TaskType;
  maxTokens?: number;
  traceId?: string;
}

export class ModelClient {
  constructor(private readonly router: LLMRouter) {}

  async complete(input: ModelCompleteInput): Promise<LLMResponse> {
    const request: LLMRequest = {
      requestId: input.requestId,
      tenantId: input.tenantId,
      userId: input.userId,
      taskType: input.taskType ?? "chat",
      prompt: input.prompt,
      maxTokens: input.maxTokens ?? 1000,
      traceId: input.traceId ?? input.requestId,
    };
    return this.router.route(request);
  }
}
