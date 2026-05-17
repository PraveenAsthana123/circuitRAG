import { LLMRequest, ModelConfig } from "./types";

export class RoutingPolicy {
  selectModel(request: LLMRequest, candidates: ModelConfig[]): ModelConfig {
    const affordable = candidates.filter(
      (m) => this.estimateCost(request, m) <= 1.0
    );

    if (affordable.length === 0) {
      throw new Error("No affordable model candidate found");
    }

    return affordable[0];
  }

  estimateCost(request: LLMRequest, model: ModelConfig): number {
    return (request.maxTokens / 1000) * model.costPer1kTokensUsd;
  }
}
