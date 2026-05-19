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
import { CostLedger } from "./cost-ledger";
import { validateLLMResponse } from "./response-validator";
import {
  EventSink,
  StreamRoutedEventSink,
} from "../06-observability/sinks";
import { ModelCardRegistry } from "../audit/model-card";

export interface LLMRouterOptions {
  productionMode?: boolean;
  // Iter 99 (2026-05-18): pluggable sink for the three router
  // event streams (llm_route_success → log, llm_route_model_failed
  // → warn, llm_route_failure → error). Default StreamRoutedEventSink
  // preserves the multi-stream contract iter 61's drill spies on.
  // A future PrometheusEventSink / DatadogSink plugs in unchanged.
  sink?: EventSink;
  // Iter 115 (2026-05-18): when set AND productionMode is true,
  // every model selected by the router MUST have a registered
  // ModelCard (iter 111). The router calls modelCardRegistry.
  // require(modelId) before dispatching; a missing card throws
  // ModelCardMissingError and the failure is recorded as a
  // candidate failure (same shape as a model-side error).
  // When productionMode is false, the registry is ignored — dev
  // and local tests don't need cards for every model.
  modelCardRegistry?: ModelCardRegistry;
}

export class LLMRouter {
  private readonly sink: EventSink;
  constructor(
    private readonly registry: ModelRegistry,
    private readonly policy: RoutingPolicy,
    private readonly safetyGate: SafetyGate,
    private readonly client: LLMClient,
    private readonly costLedger: CostLedger = new CostLedger(),
    private readonly options: LLMRouterOptions = {},
  ) {
    if (this.options.productionMode && this.client.isProductionStub) {
      throw new Error("Production LLMRouter cannot use a stub LLMClient");
    }
    this.sink = this.options.sink ?? new StreamRoutedEventSink();
  }

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
        // Iter 115 (2026-05-18): production-mode ModelCard gate.
        // Selected model MUST have a registered card BEFORE we
        // ship traffic to it. Missing card → fail-closed; the
        // catch block records it as a candidate failure (same
        // shape as a runtime model error) so the router moves
        // on to the next candidate.
        if (this.options.productionMode && this.options.modelCardRegistry) {
          this.options.modelCardRegistry.require(selected.modelId);
        }
        const response = await this.client.complete(request, selected);
        validateLLMResponse(response);
        const isFallback = failures.length > 0;
        const enriched: LLMResponse = isFallback
          ? {
              ...response,
              fallbackUsed: true,
              primaryAttempted: failures[0].modelId,
              primaryError: failures[0].error,
            }
          : response;

        this.costLedger.record({
          requestId: request.requestId,
          tenantId: request.tenantId,
          userId: request.userId,
          modelId: enriched.modelId,
          provider: enriched.provider,
          taskType: request.taskType,
          estimatedCostUsd: enriched.estimatedCostUsd,
          timestamp: new Date().toISOString(),
        });

        this.sink.emit({
          _stream: "log",
          type: "llm_route_success",
          requestId: request.requestId,
          tenantId: request.tenantId,
          userId: request.userId,
          taskType: request.taskType,
          selectedModel: selected.modelId,
          provider: selected.provider,
          fallbackUsed: isFallback,
          fallbackChainLength: failures.length,
          latencyMs: response.latencyMs,
          estimatedCostUsd: response.estimatedCostUsd,
          tenantSpendUsd: this.costLedger.getTenantSpend(request.tenantId),
          userSpendUsd: this.costLedger.getUserSpend(request.tenantId, request.userId),
          traceId: request.traceId,
          timestamp: new Date().toISOString(),
        });

        return enriched;
      } catch (error) {
        const errMsg = error instanceof Error ? error.message : "Unknown error";
        failures.push({ modelId: selected.modelId, error: errMsg });
        this.sink.emit({
          _stream: "warn",
          type: "llm_route_model_failed",
          requestId: request.requestId,
          tenantId: request.tenantId,
          modelId: selected.modelId,
          provider: selected.provider,
          error: errMsg,
          remainingCandidates: remaining.length - 1,
          traceId: request.traceId,
          timestamp: new Date().toISOString(),
        });

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
    this.sink.emit({
      _stream: "error",
      type: "llm_route_failure",
      requestId: request.requestId,
      tenantId: request.tenantId,
      taskType: request.taskType,
      attemptedModels: failures.map((f) => f.modelId),
      error: error instanceof Error ? error.message : "Unknown error",
      durationMs: Date.now() - start,
      traceId: request.traceId,
      timestamp: new Date().toISOString(),
    });
  }
}
