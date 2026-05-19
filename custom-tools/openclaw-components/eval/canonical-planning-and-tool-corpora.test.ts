// Negative drills for Iter 118 (2026-05-18): canonical
// PlanningEvalCorpus + ToolSelectionEvalCorpus run through iter
// 113's runEval against the real Planner + ToolSelector. Completes
// the 4-domain canonical eval coverage (alongside iters 116
// guardrail + 117 citation).

import { describe, it, expect } from "vitest";
import {
  buildCanonicalPlanningCorpus,
  CANONICAL_PLANNING_THRESHOLDS,
} from "./canonical-planning-corpus";
import {
  buildCanonicalToolSelectionCorpus,
  CANONICAL_TOOL_SELECTION_THRESHOLDS,
} from "./canonical-tool-selection-corpus";
import { runEval } from "./eval-corpus";
import { Planner } from "../02-agent-runtime/planner";
import { ToolSelector } from "../10-agent-workflow/tool-selector";

describe("Iter 118a — canonical planning eval corpus (P1)", () => {
  it("BACKDOOR: corpus structure has expected categories", () => {
    const corpus = buildCanonicalPlanningCorpus();
    expect(corpus.corpusId).toBe("openclaw-canonical-planning-v1");
    expect(corpus.samples.length).toBeGreaterThanOrEqual(5);
    const cats = new Set(
      corpus.samples.map((s) => (s as { category?: string }).category),
    );
    expect(cats.has("default_path")).toBe(true);
    expect(cats.has("with_input")).toBe(true);
    expect(cats.has("complex_goal")).toBe(true);
  });

  it("BACKDOOR: default Planner meets canonical thresholds (every step's action valid)", async () => {
    const corpus = buildCanonicalPlanningCorpus();
    const report = await runEval(corpus, new Planner(), CANONICAL_PLANNING_THRESHOLDS);
    expect(report.passRate).toBe(1.0);
    expect(report.meetsThresholds).toBe(true);
  });

  it("BACKDOOR: action_validity_rate === 1.0 (every step has a valid action)", async () => {
    const corpus = buildCanonicalPlanningCorpus();
    const report = await runEval(corpus, new Planner());
    expect(report.aggregateMetrics?.action_validity_rate).toBe(1.0);
  });

  it("BACKDOOR: every plan has ≥ 1 step (minimum-steps regression)", async () => {
    const corpus = buildCanonicalPlanningCorpus();
    const report = await runEval(corpus, new Planner());
    for (const o of report.outcomes) {
      const actual = o.actual as { stepCount: number };
      expect(actual.stepCount).toBeGreaterThanOrEqual(1);
    }
  });

  it("avgStepCount aggregate is reasonable (default planner produces 2-6 steps)", async () => {
    const corpus = buildCanonicalPlanningCorpus();
    const report = await runEval(corpus, new Planner());
    const avg = report.aggregateMetrics?.avgStepCount ?? 0;
    expect(avg).toBeGreaterThanOrEqual(1);
    expect(avg).toBeLessThanOrEqual(10);
  });

  it("forensic trail: each outcome captures the full plan", async () => {
    const corpus = buildCanonicalPlanningCorpus();
    const report = await runEval(corpus, new Planner());
    for (const o of report.outcomes) {
      const actual = o.actual as { plan: { steps: unknown[] } };
      expect(actual.plan).toBeDefined();
      expect(Array.isArray(actual.plan.steps)).toBe(true);
    }
  });

  it("custom PlanProvider can swap in and run through the same corpus", async () => {
    // Future iter wires LLM-driven provider; corpus stays unchanged.
    const corpus = buildCanonicalPlanningCorpus();
    const customProvider = {
      createPlan: () => ({
        taskId: "custom",
        steps: [{ stepId: "s1", action: "respond" as const, description: "custom plan" }],
      }),
    };
    const planner = new Planner(customProvider);
    const report = await runEval(corpus, planner);
    expect(report.totalCount).toBe(corpus.samples.length);
    expect(report.passRate).toBe(1.0);  // valid action
  });
});

describe("Iter 118b — canonical tool-selection eval corpus (P1)", () => {
  it("BACKDOOR: corpus has 4 categories (explicit + 2 name-patterns + default)", () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    expect(corpus.corpusId).toBe("openclaw-canonical-tool-selection-v1");
    const cats = new Set(
      corpus.samples.map((s) => (s as { category?: string }).category),
    );
    expect(cats.has("explicit_tool")).toBe(true);
    expect(cats.has("name_pattern_quality")).toBe(true);
    expect(cats.has("name_pattern_approval")).toBe(true);
    expect(cats.has("default")).toBe(true);
  });

  it("BACKDOOR: default ToolSelector meets canonical thresholds", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector(), CANONICAL_TOOL_SELECTION_THRESHOLDS);
    expect(report.passRate).toBe(1.0);
    expect(report.meetsThresholds).toBe(true);
  });

  it("BACKDOOR: selection_correctness === 1.0", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    expect(report.aggregateMetrics?.selection_correctness).toBe(1.0);
  });

  it("BACKDOOR: explicit_tool category 100% (requiredTool always wins)", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    expect(report.aggregateMetrics?.accuracy_explicit_tool).toBe(1.0);
  });

  it("BACKDOOR: name_pattern_quality category 100% (quality keyword routes correctly)", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    expect(report.aggregateMetrics?.accuracy_name_pattern_quality).toBe(1.0);
  });

  it("BACKDOOR: name_pattern_approval category 100% (approval keyword routes correctly)", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    expect(report.aggregateMetrics?.accuracy_name_pattern_approval).toBe(1.0);
  });

  it("BACKDOOR: default category 100% (fallback to default_agent_executor)", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    expect(report.aggregateMetrics?.accuracy_default).toBe(1.0);
  });

  it("BACKDOOR: explicit_tool overrides 'quality' name-pattern (precedence regression)", async () => {
    // sel-explicit-2 has name 'quality_review' AND requiredTool 'custom_tool_explicit'.
    // The required-tool MUST win.
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    const explicit2 = report.outcomes.find((o) => o.sampleId === "sel-explicit-2");
    expect(explicit2).toBeDefined();
    expect(explicit2!.pass).toBe(true);
    expect((explicit2!.actual as { actualTool: string }).actualTool)
      .toBe("custom_tool_explicit");
  });

  it("threshold gate flags regression (passRate threshold above achievable)", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector(), { passRate: 1.01 });
    expect(report.meetsThresholds).toBe(false);
  });

  it("forensic trail: each outcome captures actualTool", async () => {
    const corpus = buildCanonicalToolSelectionCorpus();
    const report = await runEval(corpus, new ToolSelector());
    for (const o of report.outcomes) {
      const actual = o.actual as { actualTool: string };
      expect(typeof actual.actualTool).toBe("string");
    }
  });
});

describe("Iter 118 — milestone: 4 canonical eval corpora ship", () => {
  it("documentation marker — eval/ folder now ships canonical corpora for all 4 Agentic-Plan domains", async () => {
    // Catalog (kept here for grep + audit):
    //   - canonical-guardrail-corpus       (iter 116)
    //   - canonical-citation-corpus        (iter 117)
    //   - canonical-planning-corpus        (iter 118a, this file's planning describe)
    //   - canonical-tool-selection-corpus  (iter 118b, this file's tool-selection describe)
    //
    // All 4 use runEval() (iter 113) + release-gate thresholds.
    // Production replaces each in-memory SUT with the real
    // adapter (LLM-driven planner, policy-aware tool selector,
    // Qdrant retriever, Llama Guard classifier) — same corpus,
    // instant comparative metric.
    expect(true).toBe(true);
  });
});
