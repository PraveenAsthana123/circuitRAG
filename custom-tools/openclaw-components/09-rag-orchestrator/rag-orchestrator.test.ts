import { describe, it, expect } from "vitest";
import { Chunker } from "./chunker";
import { Retriever } from "./retriever";
import { Reranker } from "./reranker";
import { GroundingChecker } from "./grounding-checker";
import { CitationValidator } from "./citation-validator";
import { QualityScorer } from "./quality-scorer";
import { RAGOrchestrator } from "./rag-orchestrator";

describe("RAGOrchestrator", () => {
  it("retrieves, reranks, grounds, cites, and scores answer", async () => {
    const chunker = new Chunker();

    const chunks = chunker.chunk({
      documentId: "doc-1",
      tenantId: "tenant-1",
      text: `
        RAG systems use retrieval to fetch relevant context.
        Grounding checks help reduce hallucination.
        Citation validation improves trust.
      `,
      metadata: { source: "architecture-note" },
    });

    const orchestrator = new RAGOrchestrator(
      new Retriever(chunks),
      new Reranker(),
      new GroundingChecker(),
      new CitationValidator(),
      new QualityScorer()
    );

    const response = await orchestrator.answer({
      requestId: "req-1",
      tenantId: "tenant-1",
      userId: "user-1",
      query: "How does RAG reduce hallucination?",
      traceId: "trace-1",
    });

    expect(response.citations.length).toBeGreaterThan(0);
    expect(response.qualityScore).toBeGreaterThan(0);
  });
});
