import { LLMRequest, ModelConfig } from "./types";

export interface RoutingPolicyOptions {
  defaultMaxEstimatedCostUsd?: number;
  tenantMaxEstimatedCostUsd?: Record<string, number>;
}

export class RoutingPolicy {
  private readonly defaultMaxEstimatedCostUsd: number;
  private readonly tenantMaxEstimatedCostUsd: Record<string, number>;

  constructor(options: RoutingPolicyOptions = {}) {
    this.defaultMaxEstimatedCostUsd = options.defaultMaxEstimatedCostUsd ?? 1.0;
    this.tenantMaxEstimatedCostUsd = options.tenantMaxEstimatedCostUsd ?? {};

    if (this.defaultMaxEstimatedCostUsd < 0) {
      throw new Error("defaultMaxEstimatedCostUsd must be >= 0");
    }
    for (const [tenantId, maxCost] of Object.entries(this.tenantMaxEstimatedCostUsd)) {
      if (maxCost < 0) {
        throw new Error(`tenantMaxEstimatedCostUsd for ${tenantId} must be >= 0`);
      }
    }
  }

  selectModel(request: LLMRequest, candidates: ModelConfig[]): ModelConfig {
    const maxCost = this.maxEstimatedCostForTenant(request.tenantId);
    const affordable = candidates.filter(
      (m) => this.estimateCost(request, m) <= maxCost
    );

    if (affordable.length === 0) {
      throw new Error(
        `No affordable model candidate found for tenant ${request.tenantId} ` +
        `(max estimated cost ${maxCost} USD)`
      );
    }

    return affordable[0];
  }

  estimateCost(request: LLMRequest, model: ModelConfig): number {
    return (request.maxTokens / 1000) * model.costPer1kTokensUsd;
  }

  maxEstimatedCostForTenant(tenantId: string): number {
    return this.tenantMaxEstimatedCostUsd[tenantId]
      ?? this.defaultMaxEstimatedCostUsd;
  }
}
