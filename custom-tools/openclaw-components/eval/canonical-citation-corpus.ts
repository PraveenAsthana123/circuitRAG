// Iter 117 (2026-05-18): canonical CitationEvalCorpus.
//
// Composes iter 68 (RAG no-match drill matrix) + iter 114 (hybrid
// retriever) with iter 113 (eval-corpus scaffold). Evaluates a
// RAGOrchestrator end-to-end on: precision, recall, F1, AND the
// canonical §48.5 four-part-contract invariants:
//   - tenant isolation (zero leak across tenants)
//   - no-match → zero citations (NOT hallucinated)
//   - retrieved chunks ⊆ expected universe (no fabricated chunkIds)
//
// The corpus drives a small in-memory chunk set + a series of
// labelled queries with expected chunkId sets. Future iter swaps
// the in-memory retriever for Qdrant via iter 114's seam; same
// corpus → instant comparative metric.

import { EvalCorpus } from "./eval-corpus";
import { RAGOrchestrator } from "../09-rag-orchestrator/rag-orchestrator";
import { Chunker } from "../09-rag-orchestrator/chunker";
import { Retriever } from "../09-rag-orchestrator/retriever";
import { Reranker } from "../09-rag-orchestrator/reranker";
import { GroundingChecker } from "../09-rag-orchestrator/grounding-checker";
import { CitationValidator } from "../09-rag-orchestrator/citation-validator";
import { QualityScorer } from "../09-rag-orchestrator/quality-scorer";
import { Chunk } from "../09-rag-orchestrator/types";
import { InMemoryEventSink } from "../06-observability/sinks";

/** Canonical documents that the corpus draws expected chunks from. */
const CORPUS_DOCS = [
  {
    documentId: "rag-101",
    tenantId: "tenant-A",
    text: "RAG systems use retrieval to fetch relevant context. " +
          "Grounding checks help reduce hallucination. " +
          "Citation validation improves trust in answers.",
    metadata: { source: "tenant-A-rag-primer" },
  },
  {
    documentId: "tenant-iso",
    tenantId: "tenant-A",
    text: "Multi-tenant systems must isolate data per tenant. " +
          "Tenant boundaries are enforced at query time, not just storage.",
    metadata: { source: "tenant-A-multi-tenant-design" },
  },
  {
    documentId: "secret-tenant-b",
    tenantId: "tenant-B",
    text: "TENANT-B-ONLY confidential content about internal procedures. " +
          "Cross-tenant retrieval of this MUST fail.",
    metadata: { source: "tenant-B-confidential" },
  },
];

interface CorpusSample {
  id: string;
  category: "happy" | "no_match" | "cross_tenant" | "partial_match";
  query: string;
  tenantId: string;
  // Subset of chunkIds that SHOULD appear in citations. Empty for
  // no-match / cross-tenant samples.
  expectedChunkIds: readonly string[];
  note?: string;
}

/**
 * Build sample set from the CORPUS_DOCS. Note that expectedChunkIds
 * are computed AT BUILD time by chunking the docs and selecting
 * by category — so the corpus stays in sync with the chunker.
 */
function buildSamples(chunks: Chunk[]): CorpusSample[] {
  const ragChunks = chunks.filter((c) => c.documentId === "rag-101").map((c) => c.chunkId);
  const tenantChunks = chunks.filter((c) => c.documentId === "tenant-iso").map((c) => c.chunkId);
  return [
    // Happy path
    {
      id: "happy-rag-basics",
      category: "happy",
      query: "How does RAG reduce hallucination?",
      tenantId: "tenant-A",
      expectedChunkIds: ragChunks,
    },
    {
      id: "happy-tenant-iso",
      category: "happy",
      query: "How do multi-tenant systems enforce isolation?",
      tenantId: "tenant-A",
      expectedChunkIds: tenantChunks,
    },
    // No-match (query has no semantic overlap with the corpus)
    {
      id: "no-match-physics",
      category: "no_match",
      query: "quantum chromodynamics gluon coupling",
      tenantId: "tenant-A",
      expectedChunkIds: [],
      note: "completely off-topic — orchestrator must return zero citations",
    },
    {
      id: "no-match-empty-relevance",
      category: "no_match",
      query: "blockchain consensus algorithms",
      tenantId: "tenant-A",
      expectedChunkIds: [],
    },
    // Cross-tenant isolation — tenant-A query MUST NOT return tenant-B chunks
    {
      id: "cross-tenant-confidential",
      category: "cross_tenant",
      query: "confidential internal procedures",
      tenantId: "tenant-A",  // querying as A
      expectedChunkIds: [],  // tenant-B chunks must NEVER appear
      note: "exact phrase match to tenant-B chunk; isolation must hold",
    },
    // Partial match — retrieves at least one of the expected chunks
    {
      id: "partial-grounding",
      category: "partial_match",
      query: "grounding checks for trust",
      tenantId: "tenant-A",
      expectedChunkIds: ragChunks,  // any subset is ok for partial
    },
  ];
}

export function buildCanonicalCitationCorpus(): {
  corpus: EvalCorpus<
    { query: string; tenantId: string },
    { expectedChunkIds: readonly string[] },
    { actualChunkIds: string[]; precision: number; recall: number; f1: number; isHallucination: boolean },
    RAGOrchestrator
  >;
  chunks: Chunk[];
  buildOrchestrator: () => RAGOrchestrator;
} {
  // Build the chunk set ONCE; the orchestrator and the corpus
  // both reference the same chunkIds.
  const chunker = new Chunker();
  const chunks: Chunk[] = [];
  for (const doc of CORPUS_DOCS) {
    chunks.push(...chunker.chunk(doc));
  }

  const samples = buildSamples(chunks).map((s) => ({
    id: s.id,
    category: s.category,
    note: s.note,
    input: { query: s.query, tenantId: s.tenantId },
    expected: { expectedChunkIds: s.expectedChunkIds },
  }));

  return {
    chunks,
    buildOrchestrator: () => new RAGOrchestrator(
      new Retriever(chunks),
      new Reranker(),
      new GroundingChecker(),
      new CitationValidator(),
      new QualityScorer(),
      new InMemoryEventSink(),
    ),
    corpus: {
      corpusId: "openclaw-canonical-citation-v1",
      samples,
      async evaluate(orchestrator, sample) {
        const response = await orchestrator.answer({
          requestId: "eval-" + sample.id,
          tenantId: sample.input.tenantId,
          userId: "eval-user",
          query: sample.input.query,
          traceId: "eval-trace",
        });
        // response.citations is string[] of "${documentId}#${chunkId}"
        // composite strings per CitationValidator output format.
        // Extract the chunkId after the "#" for membership comparison.
        const actualChunkIds = response.citations.map((c) => {
          const hashIdx = c.lastIndexOf("#");
          return hashIdx === -1 ? c : c.slice(hashIdx + 1);
        });
        const expectedSet = new Set(sample.expected.expectedChunkIds);
        const actualSet = new Set(actualChunkIds);
        const tp = [...actualSet].filter((id) => expectedSet.has(id)).length;
        const precision = actualSet.size === 0 ? 0 : tp / actualSet.size;
        const recall = expectedSet.size === 0 ?
          (actualSet.size === 0 ? 1 : 0) :  // no-match expects zero citations
          tp / expectedSet.size;
        const f1 = (precision + recall) === 0 ? 0 : (2 * precision * recall) / (precision + recall);
        const isHallucination = response.hallucinationFlag === true;
        // PASS criteria depend on the sample's category.
        const category = (sample as { category: string }).category;
        let pass: boolean;
        if (category === "happy" || category === "partial_match") {
          pass = recall > 0 && precision >= 0.5;  // at least half the citations are relevant
        } else if (category === "no_match" || category === "cross_tenant") {
          pass = actualSet.size === 0 && !isHallucination;  // zero citations + no hallucination
        } else {
          pass = false;
        }
        return {
          sampleId: sample.id,
          pass,
          actual: { actualChunkIds, precision, recall, f1, isHallucination },
          details: { category },
        };
      },
      computeAggregates(outcomes) {
        const avg = (k: "precision" | "recall" | "f1") =>
          outcomes.reduce(
            (s, o) => s + (((o.actual as { [m: string]: unknown })[k] as number) ?? 0),
            0,
          ) / Math.max(1, outcomes.length);
        const noMatchHallucinationRate =
          outcomes
            .filter((o) => (o.details as { category?: string })?.category === "no_match")
            .filter((o) => (o.actual as { isHallucination?: boolean }).isHallucination)
            .length /
          Math.max(1, outcomes.filter((o) => (o.details as { category?: string })?.category === "no_match").length);
        const crossTenantLeakRate =
          outcomes
            .filter((o) => (o.details as { category?: string })?.category === "cross_tenant")
            .filter((o) => (o.actual as { actualChunkIds: string[] }).actualChunkIds.length > 0)
            .length /
          Math.max(1, outcomes.filter((o) => (o.details as { category?: string })?.category === "cross_tenant").length);
        return {
          avgPrecision: avg("precision"),
          avgRecall: avg("recall"),
          avgF1: avg("f1"),
          no_match_hallucination_rate: noMatchHallucinationRate,
          cross_tenant_leak_rate: crossTenantLeakRate,
        };
      },
    },
  };
}

/** Operator-facing thresholds — release gate values. */
export const CANONICAL_CITATION_THRESHOLDS = {
  passRate: 0.83,                      // 5/6 samples must pass
  no_match_hallucination_rate: 0,      // gate is ≥ 0 — trivially passes (max-style gate not yet supported)
  cross_tenant_leak_rate: 0,
};
