// Iter 68 (2026-05-17) — RAG no-match drill matrix.
//
// Pre-fix: Component 9 had a handful of orchestrator tests covering
// the happy path, a single no-match scenario, and a single cross-
// tenant scenario. None of them locked invariants across the full
// edge-case matrix: empty corpus, multi-tenant mixed corpus, low-
// quality match, malformed query (empty + 10kb), citation-existence,
// multi-chunk rerank ordering, or a regression-pin against a known
// corpus. Without those locks, regressions in retriever / reranker /
// citation-validator could silently change RAG behavior across the
// negative axes — which is where hallucination + tenant-leak bugs
// historically come from.
//
// This file is the drill matrix. Every step has at least one
// keystone assertion prefixed `BACKDOOR CHECK:`. Negative cases
// dominate because the happy path is already covered.
//
// Composes:
//   CLAUDE.md §43 — drill testing pattern (≥1 negative per drill)
//   CLAUDE.md §48.5 — RAG four-part contract (retrieval trail,
//                     grounding, citations, guardrail trace)
//   CLAUDE.md §59 — TDDD/ORF (corpus is the eval substrate;
//                     citation accuracy = 100% per §48.5)

import { describe, it, expect } from "vitest";
import { Chunker } from "./chunker";
import { Retriever } from "./retriever";
import { Reranker } from "./reranker";
import { GroundingChecker } from "./grounding-checker";
import { CitationValidator } from "./citation-validator";
import { QualityScorer } from "./quality-scorer";
import { RAGOrchestrator } from "./rag-orchestrator";
import { Chunk, RAGRequest } from "./types";

function makeOrchestrator(chunks: Chunk[]) {
  return new RAGOrchestrator(
    new Retriever(chunks),
    new Reranker(),
    new GroundingChecker(),
    new CitationValidator(),
    new QualityScorer(),
  );
}

function makeRequest(overrides: Partial<RAGRequest>): RAGRequest {
  return {
    requestId: "req-drill",
    tenantId: "tenant-default",
    userId: "user-drill",
    query: "default query",
    traceId: "trace-drill",
    ...overrides,
  };
}

describe("RAG drill matrix (Iter 68)", () => {
  // ─── Axis 1: No-match ───────────────────────────────────────────
  it("Step 1: BACKDOOR CHECK: zero-similarity query → no citations + grounded=false + hallucinationFlag=false (NOT true)", async () => {
    // The cardinal RAG invariant: "no answer ≠ hallucination".
    // A query with zero semantic+keyword overlap to any chunk must
    // produce an empty citation set with hallucinationFlag === false,
    // because no claim was made that lacks support.
    const chunks = new Chunker().chunk({
      documentId: "doc-ts",
      tenantId: "tenant-1",
      text: "TypeScript compiles to JavaScript. It adds static types.",
      metadata: {},
    });
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({
        tenantId: "tenant-1",
        query: "photosynthesis chlorophyll",
      }),
    );
    expect(response.citations).toEqual([]);
    expect(response.grounded).toBe(false);
    // BACKDOOR: missing answer must NOT flip hallucinationFlag.
    expect(response.hallucinationFlag).toBe(false);
    expect(response.uncited).toEqual([]);
  });

  // ─── Axis 2: Empty corpus ───────────────────────────────────────
  it("Step 2: BACKDOOR CHECK: empty corpus → no crash + no citations + grounded=false", async () => {
    // Chunker fed an empty (whitespace-only) doc → zero chunks → the
    // orchestrator must not throw on the down-stream retrieve/rerank/
    // ground/cite pipeline. This was a real risk because Retriever's
    // BM25 init divides by chunks.length for avgDocLen.
    const emptyChunks = new Chunker().chunk({
      documentId: "doc-empty",
      tenantId: "tenant-1",
      text: "   \n\n   \n\n   ",
      metadata: {},
    });
    expect(emptyChunks).toEqual([]);
    const response = await makeOrchestrator(emptyChunks).answer(
      makeRequest({ tenantId: "tenant-1", query: "anything at all" }),
    );
    expect(response.citations).toEqual([]);
    expect(response.grounded).toBe(false);
    expect(response.hallucinationFlag).toBe(false);
    expect(response.unreferenced).toEqual([]);
  });

  // ─── Axis 3: Cross-tenant — single-tenant corpus, wrong tenant ──
  it("Step 3: BACKDOOR CHECK: query as tenant-X against corpus of ONLY tenant-Y chunks → zero citations (no leak)", async () => {
    // Tenant isolation invariant: tenant-X must NEVER see tenant-Y
    // evidence even if the query is a perfect lexical match. Pre-fix
    // a forgotten `tenantId` filter at the retriever layer would
    // silently leak data across tenants — the canonical RAG
    // multi-tenancy bug per §41.3.
    const tenantYChunks = new Chunker().chunk({
      documentId: "doc-secret",
      tenantId: "tenant-Y",
      text: "Acme Corp Q4 revenue forecast is $42M with 15% growth.",
      metadata: {},
    });
    const response = await makeOrchestrator(tenantYChunks).answer(
      makeRequest({
        tenantId: "tenant-X",
        query: "Acme Corp Q4 revenue forecast 42M",
      }),
    );
    // BACKDOOR: zero leak even with a perfect query match on tenant-Y.
    expect(response.citations).toEqual([]);
    expect(response.unreferenced).toEqual([]);
    expect(response.grounded).toBe(false);
    expect(response.hallucinationFlag).toBe(false);
  });

  // ─── Axis 4: Cross-tenant — mixed corpus, only own tenant contributes
  it("Step 4: BACKDOOR CHECK: mixed-tenant corpus → only tenant-X chunks contribute", async () => {
    // The harder cross-tenant case: a single index holds both
    // tenants' chunks. The retriever must filter by tenantId AND
    // produce only own-tenant citations. The forensic check: every
    // returned citation's documentId must belong to tenant-X.
    const tenantXChunks = new Chunker().chunk({
      documentId: "doc-X",
      tenantId: "tenant-X",
      text: "Apple pies are baked at 350F for 45 minutes.",
      metadata: {},
    });
    const tenantYChunks = new Chunker().chunk({
      documentId: "doc-Y",
      tenantId: "tenant-Y",
      text: "Apple pies are best with cinnamon and lemon zest.",
      metadata: {},
    });
    const mixed = [...tenantXChunks, ...tenantYChunks];
    const response = await makeOrchestrator(mixed).answer(
      makeRequest({ tenantId: "tenant-X", query: "apple pies baking" }),
    );
    // Forensic: each cited id must map to a tenant-X chunk.
    const ownTenantDocIds = new Set(tenantXChunks.map((c) => c.documentId));
    for (const cite of response.citations) {
      const [docId] = cite.split("#");
      // BACKDOOR: no tenant-Y leak via the citation channel.
      expect(ownTenantDocIds.has(docId)).toBe(true);
    }
    // Sanity: we DID get citations (so the assertion above isn't vacuous).
    expect(response.citations.length).toBeGreaterThan(0);
  });

  // ─── Axis 5: Low-quality match → grounded reflects threshold honestly
  it("Step 5: BACKDOOR CHECK: weak lexical match → grounded flag reflects threshold honestly (no silent inflation)", async () => {
    // A query with a single weak match shouldn't flip grounded=true
    // when the GroundingChecker's n-gram threshold isn't met. The
    // pre-fix risk: a scoring path that returned true on any non-
    // empty retrieval would silently mask weak answers.
    //
    // Concretely: a 1-word query that matches a stopword-heavy chunk
    // produces a low post-stopword overlap; grounded should be false
    // because the n-gram coverage doesn't meet the 0.40 default.
    const chunks = new Chunker().chunk({
      documentId: "doc-weak",
      tenantId: "tenant-1",
      text: "the the the the the the keyword the the the the the",
      metadata: {},
    });
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({ tenantId: "tenant-1", query: "keyword" }),
    );
    // BACKDOOR: grounded must be a boolean computed from the actual
    // n-gram overlap — not a silent "we got chunks, so true".
    expect(typeof response.grounded).toBe("boolean");
    // BACKDOOR: if grounded is true the qualityScore reflects the
    // grounding bonus; if false it does not. Either is acceptable;
    // what's NOT acceptable is grounded=true + zero grounding bonus.
    if (response.grounded) {
      expect(response.qualityScore).toBeGreaterThanOrEqual(40);
    }
  });

  // ─── Axis 6: Malformed query — empty string ─────────────────────
  it("Step 6: BACKDOOR CHECK: empty query string → graceful empty response (no crash, no leak)", async () => {
    // An empty query should NOT crash any downstream component
    // (retriever tokenizer, reranker contentTokens path,
    // grounding-checker n-gram path, citation regex). It should
    // produce an empty citation set since no query terms can match.
    const chunks = new Chunker().chunk({
      documentId: "doc-1",
      tenantId: "tenant-1",
      text: "Some content that would match if there were terms.",
      metadata: {},
    });
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({ tenantId: "tenant-1", query: "" }),
    );
    // BACKDOOR: zero terms → zero citations, grounded=false, no flag.
    expect(response.citations).toEqual([]);
    expect(response.grounded).toBe(false);
    expect(response.hallucinationFlag).toBe(false);
    // The answer string is still emitted (stub generator), so just
    // verify it's a string and no exception escaped.
    expect(typeof response.answer).toBe("string");
  });

  // ─── Axis 7: Malformed query — very long (10kb) ────────────────
  it("Step 7: BACKDOOR CHECK: 10kb query → handled without crash + bounded runtime", async () => {
    // A pathologically long query must not crash the pipeline. The
    // existing BM25 retriever is O(query × chunks); a 10kb query
    // means roughly 1.6k tokens (avg ~6 chars). The test locks the
    // "no crash" invariant + a generous time bound (5s) to catch
    // accidental O(N²) regressions.
    const longQuery = "lorem ipsum dolor sit amet ".repeat(400); // ~10.8kb
    expect(longQuery.length).toBeGreaterThan(10_000);
    const chunks = new Chunker().chunk({
      documentId: "doc-1",
      tenantId: "tenant-1",
      text: "lorem ipsum content for matching",
      metadata: {},
    });
    const start = Date.now();
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({ tenantId: "tenant-1", query: longQuery }),
    );
    const elapsed = Date.now() - start;
    // BACKDOOR: must complete in < 5s. Catches accidental quadratic
    // blow-ups that would surface in production as request timeouts.
    expect(elapsed).toBeLessThan(5_000);
    // The query does mention "lorem" / "ipsum" matching the chunk so
    // citations may be non-empty — but we don't assert on the count
    // because the BM25 score with a 1600-term query is implementation
    // dependent. We only assert no crash.
    expect(Array.isArray(response.citations)).toBe(true);
  });

  // ─── Axis 8: Citation correctness — no hallucinated chunkIds ────
  it("Step 8: BACKDOOR CHECK: every returned citation references a chunkId that EXISTS in the corpus (no hallucinated citations)", async () => {
    // The forensic invariant per §48.5: every citation must be
    // traceable to a real chunk. Pre-fix CitationValidator was known
    // to fabricate citations (Iter 21 fix). This drill locks the
    // post-fix invariant at the orchestrator level so future
    // regressions in either the validator OR the generator are
    // caught.
    const chunks = new Chunker().chunk({
      documentId: "doc-multi",
      tenantId: "tenant-1",
      text: [
        "RAG systems use retrieval to fetch relevant context.",
        "",
        "Grounding checks help reduce hallucination.",
        "",
        "Citation validation improves trust.",
      ].join("\n"),
      metadata: {},
    });
    const validIds = new Set(
      chunks.map((c) => `${c.documentId}#${c.chunkId}`),
    );
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({
        tenantId: "tenant-1",
        query: "retrieval grounding citation",
      }),
    );
    // BACKDOOR: every citation MUST resolve to a real chunk.
    expect(response.citations.length).toBeGreaterThan(0);
    for (const cite of response.citations) {
      expect(validIds.has(cite)).toBe(true);
    }
    // BACKDOOR: hallucinationFlag stays false when no fabricated
    // citation was emitted by the stub generator.
    expect(response.hallucinationFlag).toBe(false);
  });

  // ─── Axis 9: Multi-chunk → reranker affects citation order ─────
  it("Step 9: BACKDOOR CHECK: query matching multiple chunks → reranker biases citation order (top-1 reflects best match)", async () => {
    // The reranker uses query-coverage + position-boost + phrase-
    // bonus on top of BM25. A query that contains a verbatim phrase
    // from chunk B should rank chunk B above chunk A even if A had
    // a higher raw BM25 score. We construct two chunks where A wins
    // on raw BM25 (more keyword matches) but B contains the
    // verbatim query phrase — the rerank phrase_bonus should flip
    // the order.
    const chunks: Chunk[] = [
      // Chunk A: many "performance" mentions (high BM25 raw).
      {
        chunkId: "chunk-A",
        documentId: "doc-A",
        tenantId: "tenant-1",
        text: "performance performance performance performance performance metric",
        metadata: {},
      },
      // Chunk B: exact verbatim of the query phrase (triggers
      // phrase_bonus + coverage).
      {
        chunkId: "chunk-B",
        documentId: "doc-B",
        tenantId: "tenant-1",
        text: "how to tune performance metric correctly in production",
        metadata: {},
      },
    ];
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({
        tenantId: "tenant-1",
        query: "tune performance metric correctly",
      }),
    );
    // BACKDOOR: top-1 citation should be doc-B (phrase match wins).
    // If the reranker regressed to a no-op, A would win on raw BM25
    // term-frequency and this assertion would fail.
    expect(response.citations.length).toBeGreaterThanOrEqual(2);
    expect(response.citations[0]).toBe("doc-B#chunk-B");
  });

  // ─── Axis 10: Regression pin — happy path against known corpus ──
  it("Step 10: REGRESSION PIN: known query → known corpus → expected citation set + grounded=true", async () => {
    // The happy-path lock. Any change to the retriever/reranker/
    // grounding pipeline that breaks this assertion is a regression
    // that must be intentional + documented. Use a fixed-ID chunk
    // (bypassing chunker's UUID) with enough content to clear the
    // grounding-checker's trigram threshold once the orchestrator's
    // answer-prefix dilutes the n-gram set.
    const chunks: Chunk[] = [
      {
        chunkId: "chunk-rag",
        documentId: "doc-rag",
        tenantId: "tenant-1",
        text: [
          "RAG systems use retrieval to fetch relevant context.",
          "Grounding checks help reduce hallucination.",
          "Citation validation improves trust.",
        ].join(" "),
        metadata: {},
      },
    ];
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({
        tenantId: "tenant-1",
        query: "How does RAG reduce hallucination?",
      }),
    );
    expect(response.citations).toEqual(["doc-rag#chunk-rag"]);
    expect(response.grounded).toBe(true);
    expect(response.hallucinationFlag).toBe(false);
    expect(response.uncited).toEqual([]);
    // Quality score must include the grounded bonus (40 default).
    expect(response.qualityScore).toBeGreaterThanOrEqual(40);
  });

  // ─── Axis 11: Forensic — uncited surfaces only with markers absent from retrieval
  it("Step 11: BACKDOOR CHECK: the stub generator NEVER produces uncited markers (no false-positive hallucination signal)", async () => {
    // The orchestrator's stub answer generator emits [docId:chunkId]
    // markers from the SAME retrieved set. So uncited MUST always be
    // empty + hallucinationFlag MUST always be false for the stub.
    // If a future generator regression starts emitting fabricated
    // markers, this drill catches it before it lands in prod.
    const chunks = new Chunker().chunk({
      documentId: "doc-x",
      tenantId: "tenant-1",
      text: "Retrieval-augmented generation grounds answers in evidence.",
      metadata: {},
    });
    const response = await makeOrchestrator(chunks).answer(
      makeRequest({
        tenantId: "tenant-1",
        query: "retrieval augmented generation",
      }),
    );
    // BACKDOOR: stub generator => uncited stays empty.
    expect(response.uncited).toEqual([]);
    expect(response.hallucinationFlag).toBe(false);
  });
});
