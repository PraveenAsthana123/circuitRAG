// Negative drills for Iter 94 (2026-05-18): validateLLMResponse
// — the seam between LLMRouter and untrusted provider responses.
// A loose validator lets garbage responses propagate into cost-
// ledger writes, audit rows, downstream parsers. Locks every
// field's accept/reject contract.

import { describe, it, expect } from "vitest";
import {
  validateLLMResponse,
  LLMResponseValidationError,
} from "./response-validator";

const VALID = {
  modelId: "gpt-4o",
  provider: "openai",
  output: "hello",
  latencyMs: 100,
  estimatedCostUsd: 0.01,
  explanation: "ok",
};

describe("Iter 94 — validateLLMResponse shape (P1)", () => {
  it("BACKDOOR: valid response passes (positive baseline)", () => {
    expect(() => validateLLMResponse(VALID)).not.toThrow();
  });

  it("rejects non-object input (null)", () => {
    expect(() => validateLLMResponse(null)).toThrow(LLMResponseValidationError);
  });

  it("rejects non-object input (string)", () => {
    expect(() => validateLLMResponse("not an object")).toThrow(LLMResponseValidationError);
  });

  it("rejects non-object input (number)", () => {
    expect(() => validateLLMResponse(42)).toThrow(LLMResponseValidationError);
  });

  it("rejects non-object input (array)", () => {
    // Arrays ARE objects in JS — but ours expects fields by name.
    // requireNonEmptyString on missing field will throw.
    expect(() => validateLLMResponse([])).toThrow(LLMResponseValidationError);
  });

  it("BACKDOOR: rejects empty modelId", () => {
    expect(() => validateLLMResponse({ ...VALID, modelId: "" })).toThrow(/modelId/);
  });

  it("rejects whitespace-only modelId (.trim() check)", () => {
    expect(() => validateLLMResponse({ ...VALID, modelId: "   " })).toThrow(/modelId/);
  });

  it("rejects unsupported provider", () => {
    expect(() => validateLLMResponse({ ...VALID, provider: "evil-provider" }))
      .toThrow(/provider/);
  });

  it("rejects missing provider (undefined)", () => {
    const noProvider = { ...VALID } as Record<string, unknown>;
    delete noProvider.provider;
    expect(() => validateLLMResponse(noProvider)).toThrow(/provider/);
  });

  it("BACKDOOR: accepts each supported provider individually", () => {
    for (const provider of ["openai", "anthropic", "bedrock", "ollama"]) {
      expect(() => validateLLMResponse({ ...VALID, provider })).not.toThrow();
    }
  });

  it("rejects negative latencyMs", () => {
    expect(() => validateLLMResponse({ ...VALID, latencyMs: -1 })).toThrow(/latencyMs/);
  });

  it("rejects NaN latencyMs", () => {
    expect(() => validateLLMResponse({ ...VALID, latencyMs: NaN })).toThrow(/latencyMs/);
  });

  it("rejects Infinity latencyMs (not finite)", () => {
    expect(() => validateLLMResponse({ ...VALID, latencyMs: Infinity })).toThrow(/latencyMs/);
  });

  it("BACKDOOR: rejects negative estimatedCostUsd (CostLedger defense)", () => {
    expect(() => validateLLMResponse({ ...VALID, estimatedCostUsd: -0.01 }))
      .toThrow(/estimatedCostUsd/);
  });

  it("accepts zero latencyMs (free local call)", () => {
    expect(() => validateLLMResponse({ ...VALID, latencyMs: 0 })).not.toThrow();
  });

  it("accepts zero estimatedCostUsd (free local model)", () => {
    expect(() => validateLLMResponse({ ...VALID, estimatedCostUsd: 0 })).not.toThrow();
  });

  it("rejects empty output", () => {
    expect(() => validateLLMResponse({ ...VALID, output: "" })).toThrow(/output/);
  });

  it("rejects empty explanation", () => {
    expect(() => validateLLMResponse({ ...VALID, explanation: "" })).toThrow(/explanation/);
  });

  it("rejects non-boolean fallbackUsed when present", () => {
    expect(() => validateLLMResponse({ ...VALID, fallbackUsed: "yes" }))
      .toThrow(/fallbackUsed/);
  });

  it("accepts fallbackUsed=true when properly typed", () => {
    expect(() => validateLLMResponse({
      ...VALID,
      fallbackUsed: true,
      primaryAttempted: "primary-id",
      primaryError: "timeout",
    })).not.toThrow();
  });

  it("rejects non-string primaryAttempted when present", () => {
    expect(() => validateLLMResponse({ ...VALID, primaryAttempted: 42 }))
      .toThrow(/primaryAttempted/);
  });

  it("rejects non-string primaryError when present", () => {
    expect(() => validateLLMResponse({ ...VALID, primaryError: { msg: "x" } }))
      .toThrow(/primaryError/);
  });

  it("LLMResponseValidationError preserves name + message + instanceof", () => {
    try {
      validateLLMResponse(null);
      throw new Error("expected");
    } catch (e) {
      expect(e).toBeInstanceOf(LLMResponseValidationError);
      expect((e as Error).name).toBe("LLMResponseValidationError");
    }
  });
});
