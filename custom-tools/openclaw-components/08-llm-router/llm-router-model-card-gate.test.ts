// Negative drills for Iter 115 (2026-05-18): LLMRouter productionMode
// ModelCardRegistry gate. Composes iter 111 (ModelCardRegistry) with
// the LLMRouter so every production-mode model dispatch is gated on
// "the model has a registered card per §48.3".

import { describe, it, expect, vi } from "vitest";
import { LLMRouter } from "./llm-router";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { LLMClient } from "./llm-client";
import { LLMRequest, LLMResponse, ModelConfig } from "./types";
import { ModelCardRegistry } from "../audit/model-card";

class FixedClient extends LLMClient {
  async complete(_req: LLMRequest, model: ModelConfig): Promise<LLMResponse> {
    return {
      modelId: model.modelId, provider: model.provider, output: "ok",
      latencyMs: 1, estimatedCostUsd: 0.001, explanation: "test",
    };
  }
}

const M = (id: string, priority = 1): ModelConfig => ({
  modelId: id, provider: "ollama", supportedTasks: ["code"],
  costPer1kTokensUsd: 0.001, maxContextTokens: 8192,
  priority, enabled: true,
});

const REQ = (): LLMRequest => ({
  requestId: "r-1", tenantId: "t-1", userId: "u-1",
  taskType: "code", prompt: "x", maxTokens: 1000,
  traceId: "tr-1",
});

function registryWith(modelIds: string[]): ModelCardRegistry {
  const r = new ModelCardRegistry();
  for (const id of modelIds) {
    r.register({
      modelId: id, version: "v1",
      intendedUse: "Test model card for " + id,
      owner: { team: "test-team" },
      lastReviewedAt: new Date().toISOString(),
    });
  }
  return r;
}

describe("Iter 115 — LLMRouter ModelCard gate (P1)", () => {
  it("BACKDOOR: productionMode + registry rejects model without a card", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const router = new LLMRouter(
        new ModelRegistry([M("uncarded-model")]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FixedClient(),
        undefined,
        {
          productionMode: true,
          modelCardRegistry: registryWith([]),  // empty — uncarded-model has no card
        },
      );
      await expect(router.route(REQ())).rejects.toThrow();  // all candidates fail → final error
    } finally {
      warn.mockRestore();
      err.mockRestore();
    }
  });

  it("BACKDOOR: productionMode + registry ACCEPTS model WITH a card", async () => {
    const router = new LLMRouter(
      new ModelRegistry([M("carded-model")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      {
        productionMode: true,
        modelCardRegistry: registryWith(["carded-model"]),
      },
    );
    const response = await router.route(REQ());
    expect(response.modelId).toBe("carded-model");
  });

  it("BACKDOOR: dev mode (productionMode false) skips the gate (backcompat)", async () => {
    const router = new LLMRouter(
      new ModelRegistry([M("uncarded-model")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      {
        // productionMode omitted → defaults to false
        modelCardRegistry: registryWith([]),  // ignored
      },
    );
    // Should succeed despite missing card.
    const response = await router.route(REQ());
    expect(response.modelId).toBe("uncarded-model");
  });

  it("BACKDOOR: productionMode WITHOUT registry skips gate (registry is opt-in)", async () => {
    // If a caller turns on production mode but doesn't wire the
    // ModelCardRegistry, the gate doesn't fire (no card check =
    // no failures). Production code should ALWAYS wire both
    // together, but the router doesn't enforce that — composition
    // root does.
    const router = new LLMRouter(
      new ModelRegistry([M("any-model")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      { productionMode: true },  // no registry
    );
    const response = await router.route(REQ());
    expect(response.modelId).toBe("any-model");
  });

  it("BACKDOOR: gate fails one model → router falls back to next candidate", async () => {
    // Two models: m-uncarded (no card) + m-carded (has card).
    // Production mode + registry. Router tries m-uncarded first
    // (priority 1), gate fails, falls back to m-carded.
    const router = new LLMRouter(
      new ModelRegistry([
        M("m-uncarded", 1),
        M("m-carded", 2),
      ]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      {
        productionMode: true,
        modelCardRegistry: registryWith(["m-carded"]),
      },
    );
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const response = await router.route(REQ());
      expect(response.modelId).toBe("m-carded");
      expect(response.fallbackUsed).toBe(true);
      expect(response.primaryAttempted).toBe("m-uncarded");
    } finally {
      warn.mockRestore();
    }
  });

  it("BACKDOOR: gate failure surfaces ModelCardMissingError in the fallback chain log", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const router = new LLMRouter(
        new ModelRegistry([M("m-uncarded", 1), M("m-carded", 2)]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FixedClient(),
        undefined,
        {
          productionMode: true,
          modelCardRegistry: registryWith(["m-carded"]),
        },
      );
      await router.route(REQ());
      // The per-attempt warn log includes the error message.
      const failureLogs = warn.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "llm_route_model_failed");
      expect(failureLogs.length).toBe(1);
      expect(failureLogs[0].modelId).toBe("m-uncarded");
      expect(failureLogs[0].error).toMatch(/model card/i);
    } finally {
      warn.mockRestore();
    }
  });

  it("regression iter 96: productionMode + EchoLLMClient still rejects at construction", () => {
    // Iter 96 abstract-class guard cooperates with the new gate.
    class EchoLikeClient extends LLMClient {
      override readonly isProductionStub = true;
      async complete() {
        return {
          modelId: "x", provider: "ollama" as const, output: "",
          latencyMs: 0, estimatedCostUsd: 0, explanation: "",
        };
      }
    }
    expect(() => new LLMRouter(
      new ModelRegistry([]),
      new RoutingPolicy(),
      new SafetyGate(),
      new EchoLikeClient(),
      undefined,
      {
        productionMode: true,
        modelCardRegistry: registryWith(["any"]),
      },
    )).toThrow(/stub/);
  });

  it("model card registry passed but productionMode false → cards UNCHECKED on every model", async () => {
    // Belt-and-suspenders: even if registry is wired, dev mode
    // never invokes require(). Drill that dev-mode behavior is
    // 100% identical to no-registry behavior.
    const router1 = new LLMRouter(
      new ModelRegistry([M("uncarded")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      { productionMode: false, modelCardRegistry: registryWith([]) },
    );
    const router2 = new LLMRouter(
      new ModelRegistry([M("uncarded")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      { productionMode: false },
    );
    const r1 = await router1.route(REQ());
    const r2 = await router2.route(REQ());
    expect(r1.modelId).toBe(r2.modelId);
  });

  it("when ALL models lack cards in production mode → final llm_route_failure", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const router = new LLMRouter(
        new ModelRegistry([M("u1"), M("u2"), M("u3")]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FixedClient(),
        undefined,
        {
          productionMode: true,
          modelCardRegistry: registryWith([]),  // empty — none carded
        },
      );
      await expect(router.route(REQ())).rejects.toThrow(/All 3 candidate models failed/);
      const failures = err.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "llm_route_failure");
      expect(failures.length).toBe(1);
      expect(failures[0].attemptedModels).toEqual(["u1", "u2", "u3"]);
    } finally {
      err.mockRestore();
      warn.mockRestore();
    }
  });
});
