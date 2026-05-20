import { describe, it, expect } from "vitest";
import { RAGOrchestrator, RetrievalSource } from "./rag-orchestrator";
import { Reranker } from "./reranker";
import { GroundingChecker } from "./grounding-checker";
import { CitationValidator } from "./citation-validator";
import { QualityScorer } from "./quality-scorer";
import { InMemoryEventSink } from "../06-observability/sinks";
import { RetrievedChunk } from "./types";

const CHUNK: RetrievedChunk = {
  documentId: "doc-prod",
  chunkId: "chunk-prod",
  tenantId: "tenant-A",
  text: "Production vector database evidence",
  metadata: {},
  score: 0.99,
};

function build(retriever: RetrievalSource, sink = new InMemoryEventSink()): RAGOrchestrator {
  return new RAGOrchestrator(
    retriever,
    new Reranker(),
    new GroundingChecker(),
    new CitationValidator(),
    new QualityScorer(),
    sink,
  );
}

describe("Iter 108 - RAG retrieval source injection", () => {
  it("accepts an async production retriever adapter", async () => {
    class FakeVectorDbRetriever implements RetrievalSource {
      async retrieve(query: string, tenantId: string): Promise<RetrievedChunk[]> {
        expect(query).toBe("vector evidence");
        expect(tenantId).toBe("tenant-A");
        return [CHUNK];
      }
    }

    const response = await build(new FakeVectorDbRetriever()).answer({
      requestId: "req-1",
      tenantId: "tenant-A",
      query: "vector evidence",
      traceId: "trace-1",
      userId: "user-1",
    });

    expect(response.answer).toContain("Production vector database evidence");
    expect(response.citations).toEqual(["doc-prod#chunk-prod"]);
  });

  it("keeps tenant isolation responsibility visible at the adapter boundary", async () => {
    class TenantScopedRetriever implements RetrievalSource {
      retrieve(_query: string, tenantId: string): RetrievedChunk[] {
        return tenantId === "tenant-A" ? [CHUNK] : [];
      }
    }

    const response = await build(new TenantScopedRetriever()).answer({
      requestId: "req-2",
      tenantId: "tenant-B",
      query: "vector evidence",
      traceId: "trace-2",
      userId: "user-2",
    });

    expect(response.citations).toEqual([]);
    expect(response.grounded).toBe(false);
  });

  it("emits retrievedCount from the injected adapter results", async () => {
    const sink = new InMemoryEventSink();
    await build({ retrieve: () => [CHUNK] }, sink).answer({
      requestId: "req-3",
      tenantId: "tenant-A",
      query: "vector evidence",
      traceId: "trace-3",
      userId: "user-3",
    });

    expect(sink.list()[0].type).toBe("rag_orchestration");
    expect(sink.list()[0].retrievedCount).toBe(1);
  });
});
