// ✅ P0 FIXED (2026-05-17): LLMClient is now ABSTRACT.
//     Pre-fix: `complete()` returned a fake string like "Model X
//     answered: <prompt>". Tests passed, demos worked, but every
//     deployment shipped fake responses with no warning.
//
//     Now: LLMClient is a base class with an abstract complete()
//     method. Concrete providers must subclass and implement.
//
//     This file also ships an EchoLLMClient subclass that
//     explicitly identifies itself as a NON-production stub, so
//     interview / demo code can still wire something up — but every
//     response carries `output: "[ECHO STUB - NOT PRODUCTION]: ..."`
//     so anyone reading downstream output sees the stub marker.
//
//     For real deployments, subclass LLMClient with
//     OpenAILLMClient / AnthropicLLMClient / BedrockLLMClient /
//     OllamaLLMClient bound to the real provider SDK.

import { LLMRequest, LLMResponse, ModelConfig } from "./types";

export abstract class LLMClient {
  constructor() {
    // TS `abstract` is compile-time only; this runtime guard
    // refuses construction if a caller circumvents the type
    // checker (e.g., via JS or @ts-ignore).
    if (new.target === LLMClient) {
      throw new Error(
        "LLMClient is abstract — subclass with a real provider " +
        "(OpenAILLMClient / AnthropicLLMClient / OllamaLLMClient / ...) " +
        "before constructing."
      );
    }
  }

  abstract complete(
    request: LLMRequest,
    model: ModelConfig
  ): Promise<LLMResponse>;

  /**
   * Shared cost estimator. Subclasses can override if their pricing
   * model differs (e.g., distinct prompt vs completion token cost).
   */
  protected estimateCostUsd(request: LLMRequest, model: ModelConfig): number {
    return (request.maxTokens / 1000) * model.costPer1kTokensUsd;
  }
}

/**
 * Non-production echo stub. Identifies itself with the
 * `[ECHO STUB - NOT PRODUCTION]:` prefix so downstream code or
 * humans can spot it in audit rows / logs.
 */
export class EchoLLMClient extends LLMClient {
  async complete(
    request: LLMRequest,
    model: ModelConfig
  ): Promise<LLMResponse> {
    const start = Date.now();
    const output = `[ECHO STUB - NOT PRODUCTION]: Model ${model.modelId} would have answered: ${request.prompt}`;
    return {
      modelId: model.modelId,
      provider: model.provider,
      output,
      latencyMs: Date.now() - start,
      estimatedCostUsd: this.estimateCostUsd(request, model),
      explanation:
        `EchoLLMClient is a stub; selected ${model.modelId} per routing policy ` +
        `but did NOT call a real provider. Replace with a real subclass before deploy.`,
    };
  }
}
