import { Retriever } from "./retriever";
import { Reranker } from "./reranker";
import { GroundingChecker } from "./grounding-checker";
import { CitationValidator } from "./citation-validator";
import { QualityScorer } from "./quality-scorer";
import { RAGRequest, RAGResponse } from "./types";

export class RAGOrchestrator {
  constructor(
    private readonly retriever: Retriever,
    private readonly reranker: Reranker,
    private readonly groundingChecker: GroundingChecker,
    private readonly citationValidator: CitationValidator,
    private readonly qualityScorer: QualityScorer
  ) {}

  async answer(request: RAGRequest): Promise<RAGResponse> {
    const start = Date.now();

    const retrieved = this.retriever.retrieve(
      request.query,
      request.tenantId
    );

    const reranked = this.reranker.rerank(request.query, retrieved);

    const answer = this.generateAnswer(request.query, reranked);

    const grounded = this.groundingChecker.check(answer, reranked);

    const citations = this.citationValidator.validate(reranked);

    const qualityScore = this.qualityScorer.score(
      answer,
      reranked,
      grounded
    );

    console.log(JSON.stringify({
      type: "rag_orchestration",
      requestId: request.requestId,
      tenantId: request.tenantId,
      retrievedCount: retrieved.length,
      rerankedCount: reranked.length,
      grounded,
      qualityScore,
      durationMs: Date.now() - start,
      traceId: request.traceId,
      timestamp: new Date().toISOString(),
    }));

    return {
      answer,
      citations,
      grounded,
      qualityScore,
    };
  }

  private generateAnswer(query: string, chunks: { text: string }[]): string {
    const context = chunks.map((c) => c.text).join("\n---\n");

    return `Based on retrieved evidence, the answer to "${query}" is:\n\n${context}`;
  }
}
