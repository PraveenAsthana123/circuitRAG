import { describe, it, expect } from "vitest";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient, EchoLLMClient } from "./llm-client";
import { CostLedger } from "./cost-ledger";
import { LLMRouter } from "./llm-router";
import { LLMRequest, LLMResponse, ModelConfig } from "./types";

class InvalidResponseClient extends LLMClient {
  async complete(_request: LLMRequest, _model: ModelConfig): Promise<LLMResponse> {
    return {
      modelId: "",
      provider: "openai",
      output: "",
      latencyMs: -1,
      estimatedCostUsd: Number.NaN,
      explanation: "",
    };
  }
}

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

  it("accumulates successful route cost by tenant and user", async () => {
    const ledger = new CostLedger();
    const router = new LLMRouter(
      new ModelRegistry([
        {
          modelId: "paid-chat",
          provider: "openai",
          supportedTasks: ["chat"],
          costPer1kTokensUsd: 0.02,
          maxContextTokens: 8192,
          priority: 1,
          enabled: true,
        },
      ]),
      new RoutingPolicy(),
      new SafetyGate(),
      new EchoLLMClient(),
      ledger,
    );

    await router.route({
      requestId: "req-cost-1",
      tenantId: "tenant-cost",
      userId: "user-a",
      taskType: "chat",
      prompt: "hello",
      maxTokens: 1000,
      traceId: "trace-cost-1",
    });
    await router.route({
      requestId: "req-cost-2",
      tenantId: "tenant-cost",
      userId: "user-a",
      taskType: "chat",
      prompt: "hello again",
      maxTokens: 500,
      traceId: "trace-cost-2",
    });

    expect(ledger.getTenantSpend("tenant-cost")).toBeCloseTo(0.03);
    expect(ledger.getUserSpend("tenant-cost", "user-a")).toBeCloseTo(0.03);
    expect(ledger.getUserSpend("tenant-cost", "user-b")).toBe(0);
    expect(ledger.listEntries()).toHaveLength(2);
  });

  it("uses tenant-specific max estimated cost when choosing a model", async () => {
    const router = new LLMRouter(
      new ModelRegistry([
        {
          modelId: "expensive-primary",
          provider: "openai",
          supportedTasks: ["chat"],
          costPer1kTokensUsd: 2.0,
          maxContextTokens: 8192,
          priority: 1,
          enabled: true,
        },
        {
          modelId: "affordable-secondary",
          provider: "ollama",
          supportedTasks: ["chat"],
          costPer1kTokensUsd: 0.1,
          maxContextTokens: 8192,
          priority: 2,
          enabled: true,
        },
      ]),
      new RoutingPolicy({
        tenantMaxEstimatedCostUsd: {
          "tenant-budget": 0.5,
        },
      }),
      new SafetyGate(),
      new EchoLLMClient(),
    );

    const response = await router.route({
      requestId: "req-budget",
      tenantId: "tenant-budget",
      userId: "user-budget",
      taskType: "chat",
      prompt: "hello",
      maxTokens: 1000,
      traceId: "trace-budget",
    });

    expect(response.modelId).toBe("affordable-secondary");
  });

  it("throws when every candidate exceeds the tenant cost cap", async () => {
    const router = new LLMRouter(
      new ModelRegistry([
        {
          modelId: "expensive-only",
          provider: "openai",
          supportedTasks: ["chat"],
          costPer1kTokensUsd: 2.0,
          maxContextTokens: 8192,
          priority: 1,
          enabled: true,
        },
      ]),
      new RoutingPolicy({ tenantMaxEstimatedCostUsd: { "tenant-low": 0.5 } }),
      new SafetyGate(),
      new EchoLLMClient(),
    );

    await expect(router.route({
      requestId: "req-budget-reject",
      tenantId: "tenant-low",
      userId: "user-low",
      taskType: "chat",
      prompt: "hello",
      maxTokens: 1000,
      traceId: "trace-budget-reject",
    })).rejects.toThrow(/No affordable model candidate found/);
  });

  it("rejects invalid negative routing budget config", () => {
    expect(() => new RoutingPolicy({ defaultMaxEstimatedCostUsd: -0.01 }))
      .toThrow(/defaultMaxEstimatedCostUsd/);
    expect(() => new RoutingPolicy({
      tenantMaxEstimatedCostUsd: { "tenant-bad": -0.01 },
    })).toThrow(/tenant-bad/);
  });

  it("rejects provider responses that do not match LLMResponse shape", async () => {
    const router = new LLMRouter(
      new ModelRegistry([
        {
          modelId: "broken",
          provider: "openai",
          supportedTasks: ["chat"],
          costPer1kTokensUsd: 0,
          maxContextTokens: 8192,
          priority: 1,
          enabled: true,
        },
      ]),
      new RoutingPolicy(),
      new SafetyGate(),
      new InvalidResponseClient(),
    );

    await expect(router.route({
      requestId: "req-invalid",
      tenantId: "tenant-invalid",
      userId: "user-invalid",
      taskType: "chat",
      prompt: "hello",
      maxTokens: 100,
      traceId: "trace-invalid",
    })).rejects.toThrow(/modelId must be a non-empty string/);
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
