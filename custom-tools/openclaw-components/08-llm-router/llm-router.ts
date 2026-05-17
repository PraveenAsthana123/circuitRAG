// ✅ Iter 17 (2026-05-17): fallback model on primary failure.
//     Pre-fix: when the primary model failed (timeout, 5xx, quota,
//     filter), the whole route() rejected. The caller had to know
//     to retry against a different model.
//
//     Now: the router walks the candidate list in priority order.
//     If the highest-priority pick fails, the router logs the
//     failure, tries the next candidate that the policy approves,
//     and so on until one succeeds OR all are exhausted. The
//     successful response carries fallbackUsed: true plus the
//     primary that was attempted (for observability).
//
//     Per CLAUDE.md §38 fallback-model gate.

import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient } from "./llm-client";
import { LLMRequest, LLMResponse, ModelConfig } from "./types";

export class LLMRouter {
  constructor(
    private readonly registry: ModelRegistry,
    private readonly policy: RoutingPolicy,
    private readonly safetyGate: SafetyGate,
    private readonly client: LLMClient
  ) {}

  async route(request: LLMRequest): Promise<LLMResponse> {
    const start = Date.now();

    this.safetyGate.validate(request);

    const candidates = this.registry.findCandidates(request.taskType);
    if (candidates.length === 0) {
      throw new Error(`No model supports task type: ${request.taskType}`);
    }

    // Walk the candidate list. Stop at the first success; collect
    // failures for observability.
    const failures: { modelId: string; error: string }[] = [];
    let remaining = candidates.slice();

    while (remaining.length > 0) {
      let selected: ModelConfig;
      try {
        selected = this.policy.selectModel(request, remaining);
      } catch (policyError) {
        // No affordable / acceptable candidate left.
        this.logFailure(request, start, failures, policyError);
        throw policyError;
      }

      try {
        const response = await this.client.complete(request, selected);
        const isFallback = failures.length > 0;
        const enriched: LLMResponse = isFallback
          ? {
              ...response,
              fallbackUsed: true,
              primaryAttempted: failures[0].modelId,
              primaryError: failures[0].error,
            }
          : response;

        console.log(JSON.stringify({
          type: "llm_route_success",
          requestId: request.requestId,
          tenantId: request.tenantId,
          taskType: request.taskType,
          selectedModel: selected.modelId,
          provider: selected.provider,
          fallbackUsed: isFallback,
          fallbackChainLength: failures.length,
          latencyMs: response.latencyMs,
          estimatedCostUsd: response.estimatedCostUsd,
          traceId: request.traceId,
          timestamp: new Date().toISOString(),
        }));

        return enriched;
      } catch (error) {
        const errMsg = error instanceof Error ? error.message : "Unknown error";
        failures.push({ modelId: selected.modelId, error: errMsg });
        console.warn(JSON.stringify({
          type: "llm_route_model_failed",
          requestId: request.requestId,
          tenantId: request.tenantId,
          modelId: selected.modelId,
          provider: selected.provider,
          error: errMsg,
          remainingCandidates: remaining.length - 1,
          traceId: request.traceId,
          timestamp: new Date().toISOString(),
        }));

        // Remove the failed model from the remaining set so the policy
        // picks something different on the next iteration.
        remaining = remaining.filter((m) => m.modelId !== selected.modelId);
      }
    }

    // All candidates exhausted.
    const allFailedError = new Error(
      `All ${candidates.length} candidate models failed: ` +
      failures.map((f) => `${f.modelId}=${f.error}`).join("; ")
    );
    this.logFailure(request, start, failures, allFailedError);
    throw allFailedError;
  }

  private logFailure(
    request: LLMRequest,
    start: number,
    failures: { modelId: string; error: string }[],
    error: unknown,
  ): void {
    console.error(JSON.stringify({
      type: "llm_route_failure",
      requestId: request.requestId,
      tenantId: request.tenantId,
      taskType: request.taskType,
      attemptedModels: failures.map((f) => f.modelId),
      error: error instanceof Error ? error.message : "Unknown error",
      durationMs: Date.now() - start,
      traceId: request.traceId,
      timestamp: new Date().toISOString(),
    }));
  }
}
