// Negative drills for Iter 46 (2026-05-17): PolicyEngine config.

import { describe, it, expect } from "vitest";
import { PolicyEngine } from "./policy-engine";
import { GuardrailFinding } from "./types";

function f(
  ruleId: string,
  severity: GuardrailFinding["severity"],
): GuardrailFinding {
  return { ruleId, severity, message: "x" };
}

describe("PolicyEngine — config-driven (P2)", () => {
  it("default config preserves pre-fix behavior", () => {
    const e = new PolicyEngine();
    expect(e.decide([])).toBe("allow");
    expect(e.decide([f("PII_EMAIL", "low")])).toBe("allow");
    expect(e.decide([f("PII_EMAIL", "medium")])).toBe("review");
    expect(e.decide([f("PROMPT_INJECTION", "high")])).toBe("review");
    expect(e.decide([f("PII_CARD", "critical")])).toBe("block");
  });

  it("BACKDOOR CHECK: most-restrictive decision wins across findings", () => {
    const e = new PolicyEngine();
    // One critical + one medium → must be 'block', not 'review'.
    expect(e.decide([
      f("PII_CARD", "critical"),
      f("PII_EMAIL", "medium"),
    ])).toBe("block");
  });

  it("severityMap override: medical caller wants high → block", () => {
    const e = new PolicyEngine({
      severityMap: { high: "block" } as any,
    });
    expect(e.decide([f("PII_EMAIL", "high")])).toBe("block");
  });

  it("severityMap override: low-risk caller accepts medium → allow", () => {
    const e = new PolicyEngine({
      severityMap: { medium: "allow" } as any,
    });
    expect(e.decide([f("PII_EMAIL", "medium")])).toBe("allow");
  });

  it("rule override beats severity tier", () => {
    const e = new PolicyEngine({
      ruleOverrides: { PII_EMAIL: "block" },
    });
    expect(e.decide([f("PII_EMAIL", "medium")])).toBe("block");
  });

  it("most-restrictive wins even when overrides relax some rules", () => {
    const e = new PolicyEngine({
      ruleOverrides: {
        PII_EMAIL: "allow",  // relax this one
        PROMPT_INJECTION: "block",  // tighten that one
      },
    });
    expect(e.decide([
      f("PII_EMAIL", "medium"),
      f("PROMPT_INJECTION", "high"),
    ])).toBe("block");
  });

  it("unknown rule falls through to severity tier", () => {
    const e = new PolicyEngine({
      ruleOverrides: { KNOWN_RULE: "allow" },
    });
    expect(e.decide([f("UNKNOWN_RULE", "critical")])).toBe("block");
  });
});
