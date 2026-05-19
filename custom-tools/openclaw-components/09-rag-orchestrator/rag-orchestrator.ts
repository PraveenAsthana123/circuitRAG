import { Retriever } from "./retriever";
import { Reranker } from "./reranker";
import { GroundingChecker } from "./grounding-checker";
import { CitationValidator } from "./citation-validator";
import { QualityScorer } from "./quality-scorer";
import { RAGRequest, RAGResponse } from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export class RAGOrchestrator {
  private readonly sink: EventSink;
  // Iter 103 (2026-05-18): pluggable sink for rag_orchestration
  // emissions. Default ConsoleEventSink preserves backcompat.
  constructor(
    private readonly retriever: Retriever,
    private readonly reranker: Reranker,
    private readonly groundingChecker: GroundingChecker,
    private readonly citationValidator: CitationValidator,
    private readonly qualityScorer: QualityScorer,
    sink?: EventSink,
  ) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  async answer(request: RAGRequest): Promise<RAGResponse> {
    const start = Date.now();

    const retrieved = this.retriever.retrieve(
      request.query,
      request.tenantId
    );

    const reranked = this.reranker.rerank(request.query, retrieved);

    const answer = this.generateAnswer(request.query, reranked);

    const grounded = this.groundingChecker.check(answer, reranked);

    // Iter 21: real span-level citation verification.
    const citationResult = this.citationValidator.validate(answer, reranked);

    const qualityScore = this.qualityScorer.score(
      answer,
      reranked,
      grounded
    );

    this.sink.emit({
      type: "rag_orchestration",
      requestId: request.requestId,
      tenantId: request.tenantId,
      retrievedCount: retrieved.length,
      rerankedCount: reranked.length,
      grounded,
      qualityScore,
      uncitedCount: citationResult.uncited.length,
      unreferencedCount: citationResult.unreferenced.length,
      hallucinationFlag: citationResult.hallucinationFlag,
      durationMs: Date.now() - start,
      traceId: request.traceId,
      timestamp: new Date().toISOString(),
    });

    return {
      answer,
      citations: citationResult.cited,
      grounded,
      qualityScore,
      uncited: citationResult.uncited,
      unreferenced: citationResult.unreferenced,
      hallucinationFlag: citationResult.hallucinationFlag,
    };
  }

  private generateAnswer(
    query: string,
    chunks: { documentId: string; chunkId: string; text: string }[],
  ): string {
    // Stub: a real LLM call with citation-aware prompting would emit
    // [doc:chunk] markers next to claims. This stub appends a marker
    // after each chunk's text so CitationValidator has something
    // realistic to verify (Iter 21).
    const cited = chunks
      .map((c) => `${c.text} [${c.documentId}:${c.chunkId}]`)
      .join("\n---\n");
    return `Based on retrieved evidence, the answer to "${query}" is:\n\n${cited}`;
  }
}
