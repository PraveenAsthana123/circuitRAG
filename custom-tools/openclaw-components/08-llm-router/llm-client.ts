import { LLMRequest, LLMResponse, ModelConfig } from "./types";

export class LLMClient {
  async complete(
    request: LLMRequest,
    model: ModelConfig
  ): Promise<LLMResponse> {
    const start = Date.now();

    // Replace this with real provider SDK call
    const output = `Model ${model.modelId} answered: ${request.prompt}`;

    const latencyMs = Date.now() - start;

    return {
      modelId: model.modelId,
      provider: model.provider,
      output,
      latencyMs,
      estimatedCostUsd:
        (request.maxTokens / 1000) * model.costPer1kTokensUsd,
      explanation: `Selected ${model.modelId} because it supports ${request.taskType} and matched routing policy.`,
    };
  }
}
