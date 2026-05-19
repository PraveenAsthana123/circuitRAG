// Negative drills for Iter 117 (2026-05-18): canonical citation
// eval corpus runs through iter 113's runEval against the real
// RAGOrchestrator. Locks the §48.5 four-part-contract invariants
// (tenant isolation, no-match=no-citations, no hallucinated
// chunkIds) at the corpus level.

import { describe, it, expect } from "vitest";
import {
  buildCanonicalCitationCorpus,
  CANONICAL_CITATION_THRESHOLDS,
} from "./canonical-citation-corpus";
import { runEval } from "./eval-corpus";

describe("Iter 117 — canonical citation eval corpus (P1)", () => {
  it("BACKDOOR: corpus structure has 4 category types", () => {
    const { corpus } = buildCanonicalCitationCorpus();
    expect(corpus.corpusId).toBe("openclaw-canonical-citation-v1");
    expect(corpus.samples.length).toBeGreaterThanOrEqual(6);
    const categories = new Set(
      corpus.samples.map((s) => (s as { category?: string }).category),
    );
    expect(categories.has("happy")).toBe(true);
    expect(categories.has("no_match")).toBe(true);
    expect(categories.has("cross_tenant")).toBe(true);
    expect(categories.has("partial_match")).toBe(true);
  });

  it("BACKDOOR: each sample has a query + tenantId + expectedChunkIds", () => {
    const { corpus } = buildCanonicalCitationCorpus();
    for (const s of corpus.samples) {
      expect(s.input.query).toBeDefined();
      expect(s.input.tenantId).toBeDefined();
      expect(Array.isArray(s.expected.expectedChunkIds)).toBe(true);
    }
  });

  it("BACKDOOR: runEval produces a report against the real orchestrator", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    expect(report.totalCount).toBe(corpus.samples.length);
    expect(report.outcomes.length).toBe(report.totalCount);
  });

  it("BACKDOOR: no_match queries return ZERO citations (§48.5 no-hallucination contract)", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    const noMatch = report.outcomes.filter((o) =>
      (o.details as { category?: string })?.category === "no_match",
    );
    expect(noMatch.length).toBeGreaterThan(0);
    for (const o of noMatch) {
      const actual = (o.actual as { actualChunkIds: string[] });
      expect(actual.actualChunkIds.length).toBe(0);
    }
  });

  it("BACKDOOR: cross_tenant queries return ZERO citations (isolation contract)", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    const xt = report.outcomes.filter((o) =>
      (o.details as { category?: string })?.category === "cross_tenant",
    );
    expect(xt.length).toBeGreaterThan(0);
    for (const o of xt) {
      const actual = (o.actual as { actualChunkIds: string[] });
      expect(actual.actualChunkIds.length).toBe(0);
    }
  });

  it("BACKDOOR: aggregate cross_tenant_leak_rate === 0", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    expect(report.aggregateMetrics?.cross_tenant_leak_rate).toBe(0);
  });

  it("BACKDOOR: aggregate no_match_hallucination_rate === 0", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    expect(report.aggregateMetrics?.no_match_hallucination_rate).toBe(0);
  });

  it("happy path samples produce ≥1 citation", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    const happy = report.outcomes.filter((o) =>
      (o.details as { category?: string })?.category === "happy",
    );
    expect(happy.length).toBeGreaterThan(0);
    for (const o of happy) {
      const actual = (o.actual as { actualChunkIds: string[] });
      expect(actual.actualChunkIds.length).toBeGreaterThan(0);
    }
  });

  it("BACKDOOR: every retrieved chunkId belongs to the canonical chunk set (no fabricated IDs)", async () => {
    const { corpus, chunks, buildOrchestrator } = buildCanonicalCitationCorpus();
    const validChunkIds = new Set(chunks.map((c) => c.chunkId));
    const report = await runEval(corpus, buildOrchestrator());
    for (const o of report.outcomes) {
      const actual = (o.actual as { actualChunkIds: string[] });
      for (const cid of actual.actualChunkIds) {
        expect(validChunkIds.has(cid)).toBe(true);
      }
    }
  });

  it("BACKDOOR: cross_tenant retrieval cannot return tenant-B chunkIds when query is tenant-A", async () => {
    const { corpus, chunks, buildOrchestrator } = buildCanonicalCitationCorpus();
    const tenantBChunkIds = new Set(
      chunks.filter((c) => c.tenantId === "tenant-B").map((c) => c.chunkId),
    );
    expect(tenantBChunkIds.size).toBeGreaterThan(0);  // sanity — there ARE tenant-B chunks

    const report = await runEval(corpus, buildOrchestrator());
    const xt = report.outcomes.filter((o) =>
      (o.details as { category?: string })?.category === "cross_tenant",
    );
    for (const o of xt) {
      const actual = (o.actual as { actualChunkIds: string[] });
      const leaked = actual.actualChunkIds.filter((id) => tenantBChunkIds.has(id));
      expect(leaked.length).toBe(0);  // ZERO tenant-B chunks leaked
    }
  });

  it("aggregate precision/recall/F1 are populated", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    expect(report.aggregateMetrics?.avgPrecision).toBeDefined();
    expect(report.aggregateMetrics?.avgRecall).toBeDefined();
    expect(report.aggregateMetrics?.avgF1).toBeDefined();
  });

  it("canonical thresholds enforced — meets release gate", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator(), CANONICAL_CITATION_THRESHOLDS);
    expect(report.meetsThresholds).toBe(true);
  });

  it("threshold gate flags regression (passRate threshold above achievable)", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator(), { passRate: 1.01 });
    expect(report.meetsThresholds).toBe(false);
  });

  it("corpus size invariant (refuses future shrinkage)", () => {
    const { corpus } = buildCanonicalCitationCorpus();
    expect(corpus.samples.length).toBeGreaterThanOrEqual(6);
  });

  it("forensic trail: each outcome captures actualChunkIds + precision + recall + F1", async () => {
    const { corpus, buildOrchestrator } = buildCanonicalCitationCorpus();
    const report = await runEval(corpus, buildOrchestrator());
    for (const o of report.outcomes) {
      const actual = o.actual as {
        actualChunkIds: string[]; precision: number; recall: number; f1: number;
      };
      expect(Array.isArray(actual.actualChunkIds)).toBe(true);
      expect(typeof actual.precision).toBe("number");
      expect(typeof actual.recall).toBe("number");
      expect(typeof actual.f1).toBe("number");
    }
  });
});
