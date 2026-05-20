// Iter 132 (2026-05-20): drills the EU AI Act risk classifier.
// Asserts the decision tree behaves correctly per Regulation
// 2024/1689 across the 4 risk levels + edge cases.
//
// Negative assertions (≥ 3 per §43):
//   - Prohibited beats every other trigger (precedence rule)
//   - Annex III WITHOUT human-affecting decisions still high-risk
//   - Automated decisions on PII WITHOUT Annex III match → conservative
//     high-risk classification (the "better over-classify than under" rule)
//   - Minor handling adds GDPR Art. 8 to obligations on high-risk
//   - Pure content generator (no Annex III, no human interaction)
//     still triggers Art. 50 §2 mandatory disclosure
//   - Minimal risk does NOT require iter 131 KPIs (cost discipline)

import { describe, it, expect } from "vitest";
import {
  classifyRisk,
  UseCaseDescriptor,
  AnnexIIICategory,
} from "./risk-classifier";

const BASE: UseCaseDescriptor = {
  name: "test-case",
  description: "baseline minimal-risk descriptor",
  interactsWithHumans: false,
  generatesContent: false,
  processesPII: false,
  automatedDecisionsAffectingHumans: false,
  handlesMinors: false,
  safetyCritical: false,
  regulatedDataRegime: "none",
};

describe("Iter 132 — EU AI Act risk classifier (Regulation 2024/1689)", () => {

  // ─── Art. 5 prohibited (highest precedence) ────────────────

  it("BACKDOOR: social scoring by authority → PROHIBITED", () => {
    const result = classifyRisk({
      ...BASE,
      name: "city-social-credit-prototype",
      description: "rate citizens for public service access",
      prohibitedPractice: "social_scoring_by_authority",
    });
    expect(result.level).toBe("prohibited");
    expect(result.triggers[0]).toContain("Art. 5");
    expect(result.obligations[0].requirement).toContain("DO NOT DEPLOY");
  });

  it("NEGATIVE: prohibited beats every other trigger (precedence)", () => {
    // Even if the use case also matches Annex III + Art. 50 + safety-critical,
    // the prohibited classification wins (deploy-block).
    const result = classifyRisk({
      ...BASE,
      name: "kitchen-sink-prohibited",
      description: "everything at once",
      prohibitedPractice: "social_scoring_by_authority",
      annexIIICategory: "law_enforcement",
      safetyCritical: true,
      interactsWithHumans: true,
      generatesContent: true,
      automatedDecisionsAffectingHumans: true,
      processesPII: true,
    });
    expect(result.level).toBe("prohibited");
    // Only the Art. 5 trigger should be in the triggers list
    // (the classifier short-circuits — no point listing the others).
    expect(result.triggers.length).toBe(1);
  });

  // ─── Art. 6 + Annex III high-risk ──────────────────────────

  it("BACKDOOR: recruitment use case (Annex III employment) → HIGH-RISK", () => {
    const result = classifyRisk({
      ...BASE,
      name: "recruitment-ats",
      description: "automated candidate ranking",
      annexIIICategory: "employment_workers_management",
      processesPII: true,
      automatedDecisionsAffectingHumans: true,
    });
    expect(result.level).toBe("high_risk");
    expect(result.triggers.some((t) => t.includes("employment"))).toBe(true);
    expect(result.requiresAIActKPIs).toBe(true);
    expect(result.requiresFullExplainability).toBe(true);
    expect(result.requiresCounterfactual).toBe(true);  // Art. 86
    expect(result.requiresFairnessGate).toBe(true);    // Art. 15
  });

  it("BACKDOOR: high-risk obligations include Art. 9-17 + 86 (mandatory baseline)", () => {
    const result = classifyRisk({
      ...BASE,
      name: "credit-scoring",
      annexIIICategory: "essential_private_public_services",
      processesPII: true,
      automatedDecisionsAffectingHumans: true,
    });
    const clauses = result.obligations.map((o) => o.clause);
    expect(clauses).toContain("Art. 9");
    expect(clauses).toContain("Art. 10");
    expect(clauses).toContain("Art. 12");
    expect(clauses).toContain("Art. 13");
    expect(clauses).toContain("Art. 14");
    expect(clauses).toContain("Art. 15");
    expect(clauses).toContain("Art. 86");
  });

  it("NEGATIVE: handling minors adds GDPR Art. 8 to high-risk obligations", () => {
    const result = classifyRisk({
      ...BASE,
      name: "education-recommender",
      annexIIICategory: "education_vocational_training",
      processesPII: true,
      automatedDecisionsAffectingHumans: true,
      handlesMinors: true,
    });
    expect(result.level).toBe("high_risk");
    expect(result.obligations.some((o) => o.clause.includes("GDPR Art. 8"))).toBe(true);
    expect(result.triggers.some((t) => t.includes("minors"))).toBe(true);
  });

  it("NEGATIVE: regulated data regime (HIPAA) adds layered obligation on high-risk", () => {
    const result = classifyRisk({
      ...BASE,
      name: "clinical-decision-support",
      annexIIICategory: "essential_private_public_services",
      processesPII: true,
      automatedDecisionsAffectingHumans: true,
      regulatedDataRegime: "HIPAA",
    });
    expect(result.obligations.some((o) => o.clause === "HIPAA compliance")).toBe(true);
  });

  it("NEGATIVE (conservative): automated decisions on PII WITHOUT Annex III match → still high-risk", () => {
    // The §57.7 "better over-classify than under" rule. A
    // recommendation system that automates decisions on PII has
    // no explicit Annex III match but is treated as high-risk to
    // protect against regulator under-classification penalty.
    const result = classifyRisk({
      ...BASE,
      name: "novel-decision-system",
      processesPII: true,
      automatedDecisionsAffectingHumans: true,
    });
    expect(result.level).toBe("high_risk");
    expect(result.triggers.some((t) => t.includes("conservative"))).toBe(true);
  });

  it("BACKDOOR: safety-critical without Annex III → high-risk (Art. 6 §1(b))", () => {
    const result = classifyRisk({
      ...BASE,
      name: "industrial-control-system",
      safetyCritical: true,
    });
    expect(result.level).toBe("high_risk");
    expect(result.triggers).toContain("safety-critical");
  });

  // ─── Art. 50 limited risk ──────────────────────────────────

  it("BACKDOOR: chatbot that doesn't make decisions → LIMITED RISK with Art. 50 §1", () => {
    const result = classifyRisk({
      ...BASE,
      name: "support-chatbot",
      description: "answers documentation questions",
      interactsWithHumans: true,
    });
    expect(result.level).toBe("limited_risk");
    expect(result.obligations.some((o) => o.clause === "Art. 50 §1" && o.mandatory)).toBe(true);
    expect(result.requiresAIActKPIs).toBe(false);
  });

  it("BACKDOOR: content generator → LIMITED RISK with Art. 50 §2 (machine-readable mark)", () => {
    const result = classifyRisk({
      ...BASE,
      name: "image-generator",
      description: "generates marketing images",
      generatesContent: true,
    });
    expect(result.level).toBe("limited_risk");
    const art50_2 = result.obligations.find((o) => o.clause === "Art. 50 §2");
    expect(art50_2).toBeDefined();
    expect(art50_2!.mandatory).toBe(true);
    expect(art50_2!.requirement).toContain("machine-readable");
  });

  it("NEGATIVE: pure content generator does NOT require iter 131 EU AI Act KPIs", () => {
    // Limited risk has Art. 50 disclosure but not Art. 15
    // robustness or Art. 86 right-to-explanation. Iter 131
    // KPIs are HIGH-RISK gates, not limited-risk gates.
    const result = classifyRisk({
      ...BASE, name: "gen", generatesContent: true,
    });
    expect(result.level).toBe("limited_risk");
    expect(result.requiresAIActKPIs).toBe(false);
    expect(result.requiresCounterfactual).toBe(false);
    expect(result.requiresFairnessGate).toBe(false);
  });

  // ─── Minimal risk ──────────────────────────────────────────

  it("BACKDOOR: log-search assistant (no triggers) → MINIMAL RISK", () => {
    const result = classifyRisk({
      ...BASE,
      name: "internal-log-search",
      description: "engineer-facing log query tool",
    });
    expect(result.level).toBe("minimal_risk");
    expect(result.requiresAIActKPIs).toBe(false);
    expect(result.obligations[0].requirement).toContain("model card");
    expect(result.obligations[0].mandatory).toBe(false);
  });

  // ─── Composability with iter 131 ───────────────────────────

  it("BACKDOOR: high-risk classification flags requiresAIActKPIs=true (composes with iter 131 disclosure set)", () => {
    const hr = classifyRisk({
      ...BASE,
      name: "loan-app",
      annexIIICategory: "essential_private_public_services",
      processesPII: true,
      automatedDecisionsAffectingHumans: true,
    });
    expect(hr.requiresAIActKPIs).toBe(true);

    const minimal = classifyRisk({ ...BASE, name: "log-search" });
    expect(minimal.requiresAIActKPIs).toBe(false);
  });

  // ─── Audit trail ───────────────────────────────────────────

  it("BACKDOOR: every classification carries useCaseName + classifiedAt + triggers (audit row)", () => {
    const result = classifyRisk({ ...BASE, name: "audit-trail-test" });
    expect(result.useCaseName).toBe("audit-trail-test");
    expect(result.classifiedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(result.triggers.length).toBeGreaterThanOrEqual(1);
  });
});
