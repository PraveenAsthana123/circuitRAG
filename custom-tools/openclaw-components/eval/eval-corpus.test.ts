// Negative drills for Iter 113 (2026-05-18): eval-corpus scaffold.
// Locks the runEval contract (passRate computation, threshold gate,
// aggregate metric integration) using a tiny test SUT for each of
// the 4 canonical corpus shapes.

import { describe, it, expect } from "vitest";
import {
  EvalCorpus,
  EvalSample,
  EvalOutcome,
  GuardrailEvalCorpus,
  CitationEvalCorpus,
  runEval,
} from "./eval-corpus";

// ─────────────────────────────────────────────────────────────
// Minimal test SUTs — just enough to exercise runEval semantics
// without depending on the real planner / guardrail / orchestrator.
// ─────────────────────────────────────────────────────────────

/** Echo guardrail: maps inputText to a pre-decided disposition. */
class EchoGuardrail {
  constructor(private readonly map: Record<string, "allow" | "review" | "block">) {}
  decide(text: string): "allow" | "review" | "block" {
    return this.map[text] ?? "allow";
  }
}

/** Echo retriever: maps query to a pre-decided chunkId list. */
class EchoRetriever {
  constructor(private readonly map: Record<string, string[]>) {}
  retrieve(query: string): string[] {
    return this.map[query] ?? [];
  }
}

describe("Iter 113 — runEval contract (P1)", () => {
  it("BACKDOOR: empty corpus returns 0/0/0 + passRate 0", async () => {
    const corpus: EvalCorpus<unknown, unknown, unknown, unknown> = {
      corpusId: "empty",
      samples: [],
      evaluate: async () => ({ sampleId: "", pass: true, actual: null }),
    };
    const report = await runEval(corpus, {});
    expect(report.totalCount).toBe(0);
    expect(report.passCount).toBe(0);
    expect(report.failCount).toBe(0);
    expect(report.passRate).toBe(0);
    expect(report.meetsThresholds).toBeUndefined();
  });

  it("BACKDOOR: passRate computed correctly (3/5 = 0.6)", async () => {
    const samples: EvalSample<number, number>[] = [
      { id: "a", input: 1, expected: 1 },
      { id: "b", input: 2, expected: 2 },
      { id: "c", input: 3, expected: 3 },
      { id: "d", input: 4, expected: 99 },  // will fail
      { id: "e", input: 5, expected: 99 },  // will fail
    ];
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "test",
      samples,
      evaluate: async (_sut, s) => ({
        sampleId: s.id,
        pass: s.input === s.expected,
        actual: s.input,
      }),
    };
    const report = await runEval(corpus, {});
    expect(report.passCount).toBe(3);
    expect(report.failCount).toBe(2);
    expect(report.totalCount).toBe(5);
    expect(report.passRate).toBeCloseTo(0.6);
  });

  it("BACKDOOR: threshold passRate enforcement — passes when actual ≥ threshold", async () => {
    const samples: EvalSample<number, number>[] = [
      { id: "a", input: 1, expected: 1 },
      { id: "b", input: 2, expected: 2 },
    ];
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "t",
      samples,
      evaluate: async (_, s) => ({ sampleId: s.id, pass: true, actual: s.input }),
    };
    const report = await runEval(corpus, {}, { passRate: 0.9 });
    expect(report.passRate).toBe(1.0);
    expect(report.meetsThresholds).toBe(true);
  });

  it("BACKDOOR: threshold passRate gates — meetsThresholds false when below", async () => {
    const samples: EvalSample<number, number>[] = [
      { id: "a", input: 1, expected: 1 },
      { id: "b", input: 2, expected: 99 },  // fails
    ];
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "t",
      samples,
      evaluate: async (_, s) => ({
        sampleId: s.id, pass: s.input === s.expected, actual: s.input,
      }),
    };
    const report = await runEval(corpus, {}, { passRate: 0.9 });
    expect(report.passRate).toBe(0.5);
    expect(report.meetsThresholds).toBe(false);  // 0.5 < 0.9
  });

  it("BACKDOOR: aggregate metrics computed by corpus.computeAggregates", async () => {
    const samples: EvalSample<number, number>[] = [
      { id: "a", input: 10, expected: 10 },
      { id: "b", input: 20, expected: 20 },
    ];
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "agg",
      samples,
      evaluate: async (_, s) => ({ sampleId: s.id, pass: true, actual: s.input }),
      computeAggregates: (outcomes) => ({
        avgActual: outcomes.reduce((sum, o) => sum + (o.actual as number), 0) / outcomes.length,
      }),
    };
    const report = await runEval(corpus, {});
    expect(report.aggregateMetrics?.avgActual).toBe(15);
  });

  it("BACKDOOR: aggregate-metric threshold enforced (custom-metric gate)", async () => {
    const samples: EvalSample<number, number>[] = [
      { id: "a", input: 1, expected: 1 },
    ];
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "agg-gate",
      samples,
      evaluate: async (_, s) => ({ sampleId: s.id, pass: true, actual: s.input }),
      computeAggregates: () => ({ faithfulness: 0.7 }),
    };
    const ok = await runEval(corpus, {}, { faithfulness: 0.5 });
    expect(ok.meetsThresholds).toBe(true);

    const fail = await runEval(corpus, {}, { faithfulness: 0.85 });
    expect(fail.meetsThresholds).toBe(false);  // 0.7 < 0.85
  });

  it("aggregate-metric missing → meetsThresholds false (forensic completeness)", async () => {
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "missing-agg",
      samples: [{ id: "a", input: 1, expected: 1 }],
      evaluate: async (_, s) => ({ sampleId: s.id, pass: true, actual: s.input }),
      // No computeAggregates — `faithfulness` will be missing.
    };
    const report = await runEval(corpus, {}, { faithfulness: 0.85 });
    expect(report.meetsThresholds).toBe(false);  // missing metric fails the gate
  });

  it("per-sample outcomes are returned in input order (audit-trace regression)", async () => {
    const samples: EvalSample<string, string>[] = [
      { id: "first", input: "1", expected: "1" },
      { id: "second", input: "2", expected: "2" },
      { id: "third", input: "3", expected: "3" },
    ];
    const corpus: EvalCorpus<string, string, string, unknown> = {
      corpusId: "ordered",
      samples,
      evaluate: async (_, s) => ({ sampleId: s.id, pass: true, actual: s.input }),
    };
    const report = await runEval(corpus, {});
    expect(report.outcomes.map((o) => o.sampleId)).toEqual(["first", "second", "third"]);
  });

  it("report carries corpusId for downstream dashboards", async () => {
    const corpus: EvalCorpus<number, number, number, unknown> = {
      corpusId: "my-canonical-corpus-v1",
      samples: [{ id: "a", input: 1, expected: 1 }],
      evaluate: async (_, s) => ({ sampleId: s.id, pass: true, actual: s.input }),
    };
    const report = await runEval(corpus, {});
    expect(report.corpusId).toBe("my-canonical-corpus-v1");
  });
});

describe("Iter 113 — GuardrailEvalCorpus (canonical shape)", () => {
  it("BACKDOOR: TPR + FPR computed via computeAggregates", async () => {
    const samples: EvalSample<{ inputText: string }, { expectedDisposition: "allow" | "review" | "block" }>[] = [
      { id: "attack1", category: "attack", input: { inputText: "ignore previous" }, expected: { expectedDisposition: "block" } },
      { id: "attack2", category: "attack", input: { inputText: "reveal prompt" }, expected: { expectedDisposition: "block" } },
      { id: "clean1", category: "clean", input: { inputText: "summarize this" }, expected: { expectedDisposition: "allow" } },
      { id: "clean2", category: "clean", input: { inputText: "translate this" }, expected: { expectedDisposition: "allow" } },
    ];
    const guardrail = new EchoGuardrail({
      "ignore previous": "block",
      "reveal prompt": "block",
      "summarize this": "allow",
      "translate this": "allow",
    });

    const corpus: GuardrailEvalCorpus<EchoGuardrail> = {
      corpusId: "guardrail-test",
      samples,
      evaluate: async (g, s) => {
        const actual = g.decide(s.input.inputText);
        return {
          sampleId: s.id,
          pass: actual === s.expected.expectedDisposition,
          actual: { actualDisposition: actual },
        };
      },
      computeAggregates: (outcomes) => {
        // TPR_attack = fraction of attack samples correctly blocked.
        const attacks = outcomes.filter((o) => o.sampleId.startsWith("attack"));
        const clean = outcomes.filter((o) => o.sampleId.startsWith("clean"));
        const tpr = attacks.filter((o) => o.pass).length / attacks.length;
        const fpr = clean.filter((o) => !o.pass).length / clean.length;
        return { tpr_attack: tpr, fpr_clean: fpr };
      },
    };
    const report = await runEval(corpus, guardrail, { tpr_attack: 1.0, fpr_clean: 0.0 });
    expect(report.aggregateMetrics?.tpr_attack).toBe(1.0);
    expect(report.aggregateMetrics?.fpr_clean).toBe(0.0);
    expect(report.meetsThresholds).toBe(true);
  });
});

describe("Iter 113 — CitationEvalCorpus (canonical shape)", () => {
  it("BACKDOOR: citation precision/recall via computeAggregates", async () => {
    const samples: EvalSample<{ query: string }, { expectedChunkIds: string[] }>[] = [
      { id: "q1", input: { query: "rag basics" }, expected: { expectedChunkIds: ["c1", "c2"] } },
      { id: "q2", input: { query: "tenant iso" }, expected: { expectedChunkIds: ["c3"] } },
    ];
    const retriever = new EchoRetriever({
      "rag basics": ["c1", "c2"],          // perfect
      "tenant iso": ["c3", "c-extra"],     // 1 false-positive
    });
    const corpus: CitationEvalCorpus<EchoRetriever> = {
      corpusId: "citation-test",
      samples,
      evaluate: async (r, s) => {
        const actualChunkIds = r.retrieve(s.input.query);
        const expectedSet = new Set(s.expected.expectedChunkIds);
        const actualSet = new Set(actualChunkIds);
        const tp = [...actualSet].filter((id) => expectedSet.has(id)).length;
        const precision = actualSet.size === 0 ? 0 : tp / actualSet.size;
        const recall = expectedSet.size === 0 ? 0 : tp / expectedSet.size;
        return {
          sampleId: s.id,
          pass: precision === 1 && recall === 1,
          actual: { actualChunkIds, precision, recall },
        };
      },
      computeAggregates: (outcomes) => {
        const avg = (k: "precision" | "recall") =>
          outcomes.reduce((s, o) => s + ((o.actual as { precision?: number; recall?: number })[k] ?? 0), 0)
            / outcomes.length;
        return { avgPrecision: avg("precision"), avgRecall: avg("recall") };
      },
    };
    const report = await runEval(corpus, retriever);
    // q1 perfect (P=1, R=1), q2 P=0.5 R=1 → avgP=0.75, avgR=1.0
    expect(report.aggregateMetrics?.avgPrecision).toBeCloseTo(0.75);
    expect(report.aggregateMetrics?.avgRecall).toBe(1.0);
  });
});
