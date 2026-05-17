import { describe, it, expect } from "vitest";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient } from "./llm-client";
import { LLMRouter } from "./llm-router";

describe("LLMRouter", () => {
  it("routes code task to enabled supported model", async () => {
    const router = new LLMRouter(
      new ModelRegistry([
        {
          modelId: "local-code-model",
          provider: "ollama",
          supportedTasks: ["code"],
          costPer1kTokensUsd: 0,
          maxContextTokens: 8192,
          priority: 1,
          enabled: true,
        },
      ]),
      new RoutingPolicy(),
      new SafetyGate(),
      new LLMClient()
    );

    const response = await router.route({
      requestId: "req-1",
      tenantId: "tenant-1",
      userId: "user-1",
      taskType: "code",
      prompt: "Create TypeScript API",
      maxTokens: 1000,
      traceId: "trace-1",
    });

    expect(response.modelId).toBe("local-code-model");
  });
});
