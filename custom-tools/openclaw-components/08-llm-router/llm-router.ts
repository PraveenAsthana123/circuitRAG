import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient } from "./llm-client";
import { LLMRequest, LLMResponse } from "./types";

export class LLMRouter {
  constructor(
    private readonly registry: ModelRegistry,
    private readonly policy: RoutingPolicy,
    private readonly safetyGate: SafetyGate,
    private readonly client: LLMClient
  ) {}

  async route(request: LLMRequest): Promise<LLMResponse> {
    const start = Date.now();

    try {
      this.safetyGate.validate(request);

      const candidates = this.registry.findCandidates(request.taskType);

      if (candidates.length === 0) {
        throw new Error(`No model supports task type: ${request.taskType}`);
      }

      const selected = this.policy.selectModel(request, candidates);

      const response = await this.client.complete(request, selected);

      console.log(JSON.stringify({
        type: "llm_route_success",
        requestId: request.requestId,
        tenantId: request.tenantId,
        taskType: request.taskType,
        selectedModel: selected.modelId,
        provider: selected.provider,
        latencyMs: response.latencyMs,
        estimatedCostUsd: response.estimatedCostUsd,
        traceId: request.traceId,
        timestamp: new Date().toISOString(),
      }));

      return response;
    } catch (error) {
      console.error(JSON.stringify({
        type: "llm_route_failure",
        requestId: request.requestId,
        tenantId: request.tenantId,
        taskType: request.taskType,
        error: error instanceof Error ? error.message : "Unknown error",
        durationMs: Date.now() - start,
        traceId: request.traceId,
        timestamp: new Date().toISOString(),
      }));

      throw error;
    }
  }
}
