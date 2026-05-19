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

  it("returns no citations and ungrounded for no-match query", async () => {
    const chunks = new Chunker().chunk({
      documentId: "doc-1",
      tenantId: "tenant-1",
      text: "TypeScript compiles to JavaScript.",
      metadata: {},
    });

    const orchestrator = new RAGOrchestrator(
      new Retriever(chunks),
      new Reranker(),
      new GroundingChecker(),
      new CitationValidator(),
      new QualityScorer()
    );

    const response = await orchestrator.answer({
      requestId: "req-no-match",
      tenantId: "tenant-1",
      userId: "user-1",
      query: "quantum chromodynamics",
      traceId: "trace-no-match",
    });

    expect(response.citations).toEqual([]);
    expect(response.grounded).toBe(false);
    expect(response.hallucinationFlag).toBe(false);
  });

  it("does not retrieve another tenant evidence", async () => {
    const chunks = new Chunker().chunk({
      documentId: "doc-1",
      tenantId: "tenant-A",
      text: "RAG systems use retrieval to fetch relevant context.",
      metadata: {},
    });

    const orchestrator = new RAGOrchestrator(
      new Retriever(chunks),
      new Reranker(),
      new GroundingChecker(),
      new CitationValidator(),
      new QualityScorer()
    );

    const response = await orchestrator.answer({
      requestId: "req-tenant",
      tenantId: "tenant-B",
      userId: "user-1",
      query: "RAG retrieval context",
      traceId: "trace-tenant",
    });

    expect(response.citations).toEqual([]);
    expect(response.grounded).toBe(false);
    expect(response.unreferenced).toEqual([]);
  });
});
