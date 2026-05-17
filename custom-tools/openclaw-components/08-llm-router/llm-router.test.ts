import { describe, it, expect } from "vitest";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient, EchoLLMClient } from "./llm-client";
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
      new EchoLLMClient()
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

  it("BACKDOOR CHECK: LLMClient base class cannot be instantiated", () => {
    // Pre-fix: `new LLMClient()` succeeded and returned a fake string
    // for every prompt. Now it's abstract — TypeScript rejects
    // construction at compile time, and JS runtime rejects it via
    // the abstract modifier.
    expect(() => {
      // @ts-expect-error: instantiating an abstract class is the
      // exact thing we want to prevent. TS errors on this line; if
      // the @ts-expect-error stops applying, the abstract marker
      // has regressed.
      new LLMClient();
    }).toThrow();
  });

  it("EchoLLMClient output identifies itself as a non-production stub", async () => {
    const echo = new EchoLLMClient();
    const response = await echo.complete(
      {
        requestId: "r", tenantId: "t", userId: "u",
        taskType: "chat", prompt: "hello",
        maxTokens: 100, traceId: "tr",
      },
      {
        modelId: "stub-model", provider: "ollama",
        supportedTasks: ["chat"], costPer1kTokensUsd: 0,
        maxContextTokens: 1024, priority: 1, enabled: true,
      },
    );
    expect(response.output).toContain("[ECHO STUB - NOT PRODUCTION]");
    expect(response.explanation).toContain("did NOT call a real provider");
  });
});
