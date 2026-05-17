// Negative drills for Iter 17 (2026-05-17): LLMRouter fallback model.

import { describe, it, expect } from "vitest";
import { LLMRouter } from "./llm-router";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient } from "./llm-client";
import { LLMRequest, LLMResponse, ModelConfig } from "./types";

class FlakyClient extends LLMClient {
  constructor(private readonly failModels: Set<string>) { super(); }
  async complete(req: LLMRequest, model: ModelConfig): Promise<LLMResponse> {
    if (this.failModels.has(model.modelId)) {
      throw new Error(`provider error on ${model.modelId}`);
    }
    return {
      modelId: model.modelId,
      provider: model.provider,
      output: `ok from ${model.modelId}`,
      latencyMs: 1,
      estimatedCostUsd: 0,
      explanation: "stub",
    };
  }
}

const baseReq: LLMRequest = {
  requestId: "r", tenantId: "t", userId: "u",
  taskType: "chat", prompt: "hello", maxTokens: 100,
  traceId: "tr",
};

function makeRegistry(): ModelRegistry {
  return new ModelRegistry([
    {
      modelId: "primary",
      provider: "openai",
      supportedTasks: ["chat"],
      costPer1kTokensUsd: 0,
      maxContextTokens: 8192,
      priority: 1,
      enabled: true,
    },
    {
      modelId: "secondary",
      provider: "anthropic",
      supportedTasks: ["chat"],
      costPer1kTokensUsd: 0,
      maxContextTokens: 8192,
      priority: 2,
      enabled: true,
    },
    {
      modelId: "tertiary",
      provider: "ollama",
      supportedTasks: ["chat"],
      costPer1kTokensUsd: 0,
      maxContextTokens: 8192,
      priority: 3,
      enabled: true,
    },
  ]);
}

describe("LLMRouter — fallback model (P1)", () => {
  it("primary succeeds → no fallback flag", async () => {
    const router = new LLMRouter(
      makeRegistry(),
      new RoutingPolicy(),
      new SafetyGate(),
      new FlakyClient(new Set()),
    );
    const res = await router.route(baseReq);
    expect(res.modelId).toBe("primary");
    expect(res.fallbackUsed).toBeUndefined();
  });

  it("BACKDOOR CHECK: primary fails → secondary serves, fallbackUsed=true", async () => {
    const router = new LLMRouter(
      makeRegistry(),
      new RoutingPolicy(),
      new SafetyGate(),
      new FlakyClient(new Set(["primary"])),
    );
    const res = await router.route(baseReq);
    expect(res.modelId).toBe("secondary");
    expect(res.fallbackUsed).toBe(true);
    expect(res.primaryAttempted).toBe("primary");
    expect(res.primaryError).toMatch(/provider error/);
  });

  it("primary + secondary fail → tertiary serves", async () => {
    const router = new LLMRouter(
      makeRegistry(),
      new RoutingPolicy(),
      new SafetyGate(),
      new FlakyClient(new Set(["primary", "secondary"])),
    );
    const res = await router.route(baseReq);
    expect(res.modelId).toBe("tertiary");
    expect(res.fallbackUsed).toBe(true);
    // primaryAttempted is the FIRST one that failed (most-preferred).
    expect(res.primaryAttempted).toBe("primary");
  });

  it("all candidates fail → throws with summary of attempts", async () => {
    const router = new LLMRouter(
      makeRegistry(),
      new RoutingPolicy(),
      new SafetyGate(),
      new FlakyClient(new Set(["primary", "secondary", "tertiary"])),
    );
    await expect(router.route(baseReq)).rejects.toThrow(/All 3 candidate models failed/);
  });

  it("no candidates for task → throws (no fallback to invent)", async () => {
    const router = new LLMRouter(
      new ModelRegistry([]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FlakyClient(new Set()),
    );
    await expect(router.route(baseReq)).rejects.toThrow(/No model supports task type/);
  });
});
