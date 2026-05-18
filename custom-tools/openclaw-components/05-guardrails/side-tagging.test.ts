// Negative drills for Iter 85 (2026-05-18): GuardrailEngine side-
// tagging contract. Every finding's ruleId is prefixed with the
// side it came from (INPUT_* or OUTPUT_*) so downstream policy +
// audit can distinguish prompt-side vs response-side violations.
// Easy to silently break in a refactor; lock it explicitly.

import { describe, it, expect } from "vitest";
import { GuardrailEngine } from "./guardrail-engine";
import { PIIDetector } from "./pii-detector";
import { PromptInjectionDetector } from "./prompt-injection-detector";
import { PolicyEngine } from "./policy-engine";
import { ApprovalGate } from "./approval-gate";

const ENGINE = new GuardrailEngine(
  new PIIDetector(),
  new PromptInjectionDetector(),
  new PolicyEngine(),
  new ApprovalGate(),
);

const CTX = {
  requestId: "r", sessionId: "s", userId: "u",
  tenantId: "t", traceId: "tr",
};

describe("Iter 85 — GuardrailEngine side-tagging (P1)", () => {
  it("BACKDOOR: evaluateRequest tags every finding with INPUT_ prefix", () => {
    const result = ENGINE.evaluateRequest({
      inputText: "user email: alice@example.com",
      context: CTX,
    });
    expect(result.findings.length).toBeGreaterThan(0);
    for (const f of result.findings) {
      expect(f.ruleId).toMatch(/^INPUT_/);
    }
  });

  it("BACKDOOR: evaluateResponse tags every finding with OUTPUT_ prefix", () => {
    const result = ENGINE.evaluateResponse(
      "LLM leaked alice@example.com in response",
      CTX,
    );
    expect(result.findings.length).toBeGreaterThan(0);
    for (const f of result.findings) {
      expect(f.ruleId).toMatch(/^OUTPUT_/);
    }
  });

  it("BACKDOOR: input + output of SAME content yield differently-prefixed findings", () => {
    const text = "alice@example.com";
    const inputResult = ENGINE.evaluateRequest({ inputText: text, context: CTX });
    const outputResult = ENGINE.evaluateResponse(text, CTX);

    const inputRuleIds = inputResult.findings.map((f) => f.ruleId).sort();
    const outputRuleIds = outputResult.findings.map((f) => f.ruleId).sort();

    expect(inputRuleIds.length).toBe(outputRuleIds.length);
    // Same underlying rules, different prefixes.
    expect(inputRuleIds).not.toEqual(outputRuleIds);
    for (let i = 0; i < inputRuleIds.length; i++) {
      const inputBase = inputRuleIds[i].replace(/^INPUT_/, "");
      const outputBase = outputRuleIds[i].replace(/^OUTPUT_/, "");
      expect(inputBase).toBe(outputBase);
    }
  });

  it("clean input yields zero findings (no spurious tags)", () => {
    const result = ENGINE.evaluateRequest({
      inputText: "summarize the report please",
      context: CTX,
    });
    expect(result.findings).toEqual([]);
    expect(result.decision).toBe("allow");
  });

  it("backcompat: evaluate() delegates to evaluateRequest (still INPUT_*)", () => {
    const result = ENGINE.evaluate({
      inputText: "user email: alice@example.com",
      context: CTX,
    });
    for (const f of result.findings) {
      expect(f.ruleId).toMatch(/^INPUT_/);
    }
  });

  it("BACKDOOR: tag prefix is exactly INPUT_ or OUTPUT_ (no SIDE_ or req_ drift)", () => {
    // A refactor that changes the tag scheme would silently break
    // downstream policy rules that match by prefix string.
    const findings = [
      ...ENGINE.evaluateRequest({ inputText: "alice@x.com", context: CTX }).findings,
      ...ENGINE.evaluateResponse("alice@x.com", CTX).findings,
    ];
    expect(findings.length).toBeGreaterThan(0);
    for (const f of findings) {
      const prefix = f.ruleId.split("_")[0] + "_";
      expect(["INPUT_", "OUTPUT_"]).toContain(prefix);
    }
  });

  it("explanation text mentions the side that was evaluated", () => {
    const i = ENGINE.evaluateRequest({ inputText: "ok", context: CTX });
    const o = ENGINE.evaluateResponse("ok", CTX);
    expect(i.explanation).toContain("input");
    expect(o.explanation).toContain("output");
  });

  it("findings of zero count still carry the correct explanation side", () => {
    const i = ENGINE.evaluateRequest({ inputText: "clean", context: CTX });
    const o = ENGINE.evaluateResponse("clean", CTX);
    expect(i.findings.length).toBe(0);
    expect(o.findings.length).toBe(0);
    expect(i.explanation).toContain("(input)");
    expect(o.explanation).toContain("(output)");
  });
});
