// Negative drills for Iter 31 (2026-05-17): PII detector broader
// + severity tiers + Luhn validation.

import { describe, it, expect } from "vitest";
import { PIIDetector } from "./pii-detector";

const d = new PIIDetector();

function rules(text: string): string[] {
  return d.detect(text).map((f) => f.ruleId);
}

describe("PIIDetector — coverage (P1)", () => {
  it("detects email + phone (compat with original)", () => {
    expect(rules("alice@example.com or 415-555-1234"))
      .toEqual(expect.arrayContaining(["PII_EMAIL", "PII_PHONE"]));
  });

  it("BACKDOOR CHECK: random 16-digit string NOT flagged as card", () => {
    const findings = d.detect("tracking 1234567890123456");
    expect(findings.find((f) => f.ruleId === "PII_CARD")).toBeUndefined();
  });

  it("Luhn-valid card flagged as critical", () => {
    const findings = d.detect("paid with 4242 4242 4242 4242");
    const card = findings.find((f) => f.ruleId === "PII_CARD");
    expect(card).toBeDefined();
    expect(card!.severity).toBe("critical");
  });

  it("SSN flagged critical", () => {
    const findings = d.detect("SSN 123-45-6789");
    const ssn = findings.find((f) => f.ruleId === "PII_SSN");
    expect(ssn).toBeDefined();
    expect(ssn!.severity).toBe("critical");
  });

  it("IBAN flagged critical", () => {
    const findings = d.detect("Send to GB82WEST12345698765432");
    expect(findings.find((f) => f.ruleId === "PII_IBAN")?.severity)
      .toBe("critical");
  });

  it("IPv4 flagged high (infrastructure leak)", () => {
    expect(d.detect("server 10.0.0.5")[0].severity).toBe("high");
  });

  it("BACKDOOR CHECK: severities drive policy decisions, not just labels", () => {
    // Critical PII findings should cause the policy engine to block,
    // not just review. The PolicyEngine reads `severity` to decide.
    const findings = d.detect("My SSN is 123-45-6789");
    const sev = findings.map((f) => f.severity);
    expect(sev).toContain("critical");
  });

  it("benign text yields no findings (false-positive check)", () => {
    expect(d.detect("Order 12345 was shipped on 2026-05-17"))
      .toEqual([]);
  });

  it("international phone with country code", () => {
    expect(rules("call +44 20 7946 0958")).toContain("PII_PHONE");
  });

  it("detects multiple PII types in one input", () => {
    const r = rules("Email alice@example.com, card 4242424242424242, SSN 111-22-3333");
    expect(r).toEqual(expect.arrayContaining([
      "PII_EMAIL", "PII_CARD", "PII_SSN",
    ]));
  });
});
