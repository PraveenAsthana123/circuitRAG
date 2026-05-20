// Iter 131 (2026-05-20): drills the KPI evaluator + canonical
// catalog. Locks the §42-43 GAPS row requirements: every KPI MUST
// carry dataset + methodology + cadence + dashboardOwner + alert
// threshold + comparison direction + EU AI Act relevance flag.
//
// Negative assertions (≥ 3 per §43):
//   - Missing observation → unknown (NOT crash)
//   - kpiId mismatch (wrong observation for KPI) → unknown
//   - measured below alertThreshold (gte) → critical
//   - measured between target and alertThreshold (gte) → warn
//   - measured above alertThreshold (lte) → critical
//   - hallucination KPI uses canonical-citation corpus (NOT something else)

import { describe, it, expect } from "vitest";
import {
  CANONICAL_KPIS,
  evaluateKPI,
  evaluateAllKPIs,
  euAiActDisclosureSet,
} from "./kpi-targets";

const HALLUCINATION = CANONICAL_KPIS.find((k) => k.id === "rag_hallucination_rate")!;
const CITATION_ACCURACY = CANONICAL_KPIS.find((k) => k.id === "rag_citation_accuracy")!;
const FPR = CANONICAL_KPIS.find((k) => k.id === "guardrail_false_positive_rate")!;
const TPR = CANONICAL_KPIS.find((k) => k.id === "guardrail_true_positive_rate")!;
const TOOL = CANONICAL_KPIS.find((k) => k.id === "tool_selection_accuracy")!;
const PLAN = CANONICAL_KPIS.find((k) => k.id === "plan_action_validity")!;

describe("Iter 131 — KPI baseline methodology", () => {

  // ─── Catalog completeness ─────────────────────────────────

  it("BACKDOOR: CANONICAL_KPIS exposes 6 named KPIs", () => {
    const ids = CANONICAL_KPIS.map((k) => k.id).sort();
    expect(ids).toEqual([
      "guardrail_false_positive_rate",
      "guardrail_true_positive_rate",
      "plan_action_validity",
      "rag_citation_accuracy",
      "rag_hallucination_rate",
      "tool_selection_accuracy",
    ]);
  });

  it("BACKDOOR §42-43 GAPS row: every KPI carries the 7 mandatory protocol fields", () => {
    for (const kpi of CANONICAL_KPIS) {
      expect(kpi.evalDataset).toBeTruthy();
      expect(kpi.methodology).toBeTruthy();
      expect(kpi.methodology.length).toBeGreaterThan(20);  // not a stub
      expect(kpi.dashboardOwner).toBeTruthy();
      expect(kpi.samplingCadence).toBeTruthy();
      expect(typeof kpi.alertThreshold).toBe("number");
      expect(typeof kpi.target).toBe("number");
      expect(typeof kpi.euAiActRelevant).toBe("boolean");
      expect(Array.isArray(kpi.complianceRefs)).toBe(true);
    }
  });

  it("BACKDOOR: every KPI binds to a canonical eval dataset (not 'prod_traffic_sample')", () => {
    // The canonical KPIs MUST use a deterministic canonical corpus.
    // 'prod_traffic_sample' is allowed in the type union for custom
    // KPIs but should NOT appear in the canonical set — production
    // traffic is non-deterministic and unsuitable for per-release gates.
    for (const kpi of CANONICAL_KPIS) {
      expect(kpi.evalDataset).not.toBe("prod_traffic_sample");
    }
  });

  // ─── Source-eval binding ──────────────────────────────────

  it("BACKDOOR: hallucination KPI binds to canonical_citation_corpus (not something else)", () => {
    expect(HALLUCINATION.evalDataset).toBe("canonical_citation_corpus");
  });

  it("BACKDOOR: citation accuracy KPI is EU AI Act relevant (Art. 86 right to explanation)", () => {
    expect(CITATION_ACCURACY.euAiActRelevant).toBe(true);
    expect(CITATION_ACCURACY.complianceRefs.some((r) => r.includes("Art. 86"))).toBe(true);
  });

  it("BACKDOOR: FPR + TPR both bind to canonical_guardrail_corpus", () => {
    expect(FPR.evalDataset).toBe("canonical_guardrail_corpus");
    expect(TPR.evalDataset).toBe("canonical_guardrail_corpus");
  });

  // ─── Evaluator: happy path ────────────────────────────────

  it("BACKDOOR: hallucination 2% → meets 3% target, ok", () => {
    const result = evaluateKPI(HALLUCINATION, {
      kpiId: "rag_hallucination_rate", value: 0.02, sampleSize: 100,
    });
    expect(result.meetsTarget).toBe(true);
    expect(result.alertLevel).toBe("ok");
    expect(result.sampleSize).toBe(100);
  });

  it("BACKDOOR: citation accuracy 100% → meets 100% target", () => {
    const result = evaluateKPI(CITATION_ACCURACY, {
      kpiId: "rag_citation_accuracy", value: 1.0, sampleSize: 50,
    });
    expect(result.meetsTarget).toBe(true);
    expect(result.alertLevel).toBe("ok");
  });

  // ─── Evaluator: 3-band alarming ───────────────────────────

  it("NEGATIVE: hallucination 4% → misses 3% target but under 5% alert → WARN", () => {
    const result = evaluateKPI(HALLUCINATION, {
      kpiId: "rag_hallucination_rate", value: 0.04, sampleSize: 100,
    });
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("warn");
  });

  it("NEGATIVE: hallucination 7% → above alert threshold → CRITICAL", () => {
    const result = evaluateKPI(HALLUCINATION, {
      kpiId: "rag_hallucination_rate", value: 0.07, sampleSize: 100,
    });
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("critical");
    expect(result.reason).toContain("> target");
  });

  it("NEGATIVE: TPR 96% (gte direction) → misses 99% target but above 95% alert → WARN", () => {
    const result = evaluateKPI(TPR, {
      kpiId: "guardrail_true_positive_rate", value: 0.96, sampleSize: 14,
    });
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("warn");
  });

  it("NEGATIVE: TPR 80% → below 95% alert → CRITICAL", () => {
    const result = evaluateKPI(TPR, {
      kpiId: "guardrail_true_positive_rate", value: 0.80, sampleSize: 14,
    });
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("critical");
  });

  // ─── Defensive ────────────────────────────────────────────

  it("NEGATIVE: missing observation → unknown (NOT crash)", () => {
    const result = evaluateKPI(HALLUCINATION, undefined);
    expect(result.measuredValue).toBeUndefined();
    expect(result.alertLevel).toBe("unknown");
    expect(result.reason).toContain("No observation");
  });

  it("NEGATIVE: kpiId mismatch (wrong observation passed for KPI) → unknown", () => {
    const result = evaluateKPI(HALLUCINATION, {
      kpiId: "wrong-kpi-id", value: 0.5, sampleSize: 10,
    });
    expect(result.alertLevel).toBe("unknown");
  });

  // ─── Batch + EU AI Act disclosure ─────────────────────────

  it("BACKDOOR: evaluateAllKPIs returns 1 measurement per KPI even when observations partial", () => {
    const results = evaluateAllKPIs(CANONICAL_KPIS, [
      { kpiId: "rag_hallucination_rate", value: 0.02, sampleSize: 100 },
      { kpiId: "rag_citation_accuracy", value: 1.0, sampleSize: 50 },
    ]);
    expect(results.length).toBe(CANONICAL_KPIS.length);
    // The 2 observed → ok; the 4 unobserved → unknown
    expect(results.filter((r) => r.alertLevel === "ok").length).toBe(2);
    expect(results.filter((r) => r.alertLevel === "unknown").length).toBe(4);
  });

  it("BACKDOOR: euAiActDisclosureSet returns ONLY KPIs requiring EU AI Act disclosure", () => {
    const disclosed = euAiActDisclosureSet(CANONICAL_KPIS);
    expect(disclosed.length).toBeGreaterThan(0);
    expect(disclosed.every((k) => k.euAiActRelevant === true)).toBe(true);
    // Specifically: hallucination + citation + TPR are EU AI Act relevant
    const disclosedIds = disclosed.map((k) => k.id).sort();
    expect(disclosedIds).toContain("rag_hallucination_rate");
    expect(disclosedIds).toContain("rag_citation_accuracy");
    expect(disclosedIds).toContain("guardrail_true_positive_rate");
  });

  it("BACKDOOR: each measurement carries evalDataset + sampleSize + measuredAt (operator audit trail)", () => {
    const result = evaluateKPI(HALLUCINATION, {
      kpiId: "rag_hallucination_rate", value: 0.02, sampleSize: 100,
    });
    expect(result.evalDataset).toBe("canonical_citation_corpus");
    expect(result.sampleSize).toBe(100);
    expect(result.measuredAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });
});
