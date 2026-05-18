// Negative drills for Iter 96 (2026-05-18): LLMClient abstract-class
// runtime guard regression. Iter 10 added a `new.target === LLMClient`
// check that fails-closed if a caller circumvents `abstract` via
// JS or @ts-ignore. The drill locks that guard + its escape paths.

import { describe, it, expect } from "vitest";
import { LLMClient, EchoLLMClient } from "./llm-client";
import { LLMRequest, ModelConfig } from "./types";

describe("Iter 96 — LLMClient abstract guard (P1)", () => {
  it("BACKDOOR: direct construction of LLMClient throws", () => {
    // ts-expect-error — bypassing the abstract check (the runtime
    // guard is the whole point of this drill).
    // @ts-expect-error abstract bypass
    expect(() => new LLMClient()).toThrow(/abstract/);
  });

  it("BACKDOOR: subclass construction succeeds (EchoLLMClient)", () => {
    expect(() => new EchoLLMClient()).not.toThrow();
  });

  it("BACKDOOR: EchoLLMClient.isProductionStub === true (production gate signal)", () => {
    expect(new EchoLLMClient().isProductionStub).toBe(true);
  });

  it("Custom subclass with isProductionStub omitted defaults to false (real-provider contract)", () => {
    class FakeProviderClient extends LLMClient {
      async complete(_req: LLMRequest, model: ModelConfig) {
        return {
          modelId: model.modelId,
          provider: "openai" as const,
          output: "real",
          latencyMs: 1,
          estimatedCostUsd: 0,
          explanation: "test",
        };
      }
    }
    expect(new FakeProviderClient().isProductionStub).toBe(false);
  });

  it("EchoLLMClient.complete returns the canonical [ECHO STUB] marker", async () => {
    const client = new EchoLLMClient();
    const result = await client.complete(
      { requestId: "r", tenantId: "t", userId: "u", taskType: "code",
        prompt: "x", maxTokens: 10, traceId: "tr" },
      { modelId: "m", provider: "ollama", supportedTasks: ["code"],
        costPer1kTokensUsd: 0, maxContextTokens: 100, priority: 1, enabled: true },
    );
    expect(result.output).toContain("[ECHO STUB - NOT PRODUCTION]");
  });

  it("error message names the abstract class + suggests subclasses (audit visibility)", () => {
    try {
      // @ts-expect-error abstract bypass
      new LLMClient();
      throw new Error("expected");
    } catch (e) {
      const msg = (e as Error).message;
      expect(msg).toContain("abstract");
      expect(msg).toContain("LLMClient");
    }
  });

  it("estimateCostUsd is computable on a concrete subclass (linear in maxTokens)", () => {
    class TestClient extends LLMClient {
      async complete() {
        return { modelId: "m", provider: "ollama" as const, output: "x",
                 latencyMs: 1, estimatedCostUsd: 0, explanation: "x" };
      }
      // Expose the protected helper for testing.
      computeCost(req: LLMRequest, model: ModelConfig): number {
        // eslint-disable-next-line @typescript-eslint/dot-notation
        return (this as unknown as { estimateCostUsd: (r: LLMRequest, m: ModelConfig) => number })
          .estimateCostUsd(req, model);
      }
    }
    const c = new TestClient();
    const req: LLMRequest = {
      requestId: "r", tenantId: "t", userId: "u", taskType: "code",
      prompt: "x", maxTokens: 2000, traceId: "tr",
    };
    const model: ModelConfig = {
      modelId: "m", provider: "ollama", supportedTasks: ["code"],
      costPer1kTokensUsd: 0.5, maxContextTokens: 100, priority: 1, enabled: true,
    };
    expect(c.computeCost(req, model)).toBe(1);  // 2000/1000 * 0.5 = 1
  });

  it("constructed subclass instanceof LLMClient (prototype chain intact)", () => {
    expect(new EchoLLMClient()).toBeInstanceOf(LLMClient);
  });

  it("LLMClient base IS an Error-free class (no accidental subclassing of Error)", () => {
    // Defensive: a future refactor that accidentally has LLMClient
    // extends Error would break the abstract guard's instanceof
    // semantics. Lock the parent contract.
    expect(EchoLLMClient.prototype instanceof Error).toBe(false);
  });
});
