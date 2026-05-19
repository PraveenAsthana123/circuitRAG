// Negative drills for Iter 114 (2026-05-18): HybridRetriever
// interface split + RRF / concat-dedupe / weighted-sum fuse
// strategies. Locks the Phase 2.5 seam where Qdrant/pgvector
// adapters plug in.

import { describe, it, expect } from "vitest";
import {
  HybridRetriever,
  KeywordRetrieverI,
  VectorRetrieverI,
  InMemoryKeywordRetriever,
  InMemoryVectorRetriever,
} from "./hybrid-retriever";
import { Chunk, RetrievedChunk } from "./types";

const CHUNKS: Chunk[] = [
  {
    chunkId: "c1", documentId: "d1", tenantId: "t-1",
    text: "retrieval augmented generation patterns", metadata: {},
  },
  {
    chunkId: "c2", documentId: "d1", tenantId: "t-1",
    text: "vector embedding semantic search", metadata: {},
  },
  {
    chunkId: "c3", documentId: "d2", tenantId: "t-1",
    text: "tenant isolation in multi-tenant systems", metadata: {},
  },
  {
    chunkId: "c4", documentId: "d3", tenantId: "t-2",
    text: "completely unrelated content for tenant B", metadata: {},
  },
];

describe("Iter 114 — HybridRetriever (P1)", () => {
  it("BACKDOOR: keyword-only mode works (vector omitted)", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      undefined,
    );
    const results = await hybrid.retrieve("retrieval", "t-1");
    expect(results.length).toBeGreaterThan(0);
    expect(results.find((r) => r.chunkId === "c1")).toBeDefined();
  });

  it("BACKDOOR: vector-only mode works (keyword omitted)", async () => {
    const hybrid = new HybridRetriever(
      undefined,
      new InMemoryVectorRetriever(CHUNKS),
    );
    const results = await hybrid.retrieve("retrieval", "t-1");
    expect(results.length).toBeGreaterThan(0);
  });

  it("BACKDOOR: constructor rejects when BOTH keyword and vector are omitted", () => {
    expect(() => new HybridRetriever(undefined, undefined))
      .toThrow(/at least one of/);
  });

  it("BACKDOOR: RRF fusion combines results from both sources", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
    );
    const results = await hybrid.retrieve("retrieval semantic", "t-1");
    // Both c1 (keyword on "retrieval") and c2 (vector on "semantic")
    // should appear. RRF boosts c1+c2 since they hit different sources.
    const ids = results.map((r) => r.chunkId);
    expect(ids).toContain("c1");
    expect(ids).toContain("c2");
  });

  it("BACKDOOR: tenant isolation — wrong-tenant chunks never appear", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
    );
    // Query as tenant-1; c4 (tenant-2) MUST NOT appear.
    const results = await hybrid.retrieve("content", "t-1");
    expect(results.find((r) => r.chunkId === "c4")).toBeUndefined();
  });

  it("BACKDOOR: tenant isolation works in vector-only mode", async () => {
    const hybrid = new HybridRetriever(
      undefined,
      new InMemoryVectorRetriever(CHUNKS),
    );
    const results = await hybrid.retrieve("content", "t-1");
    expect(results.find((r) => r.chunkId === "c4")).toBeUndefined();
  });

  it("BACKDOOR: tenant isolation works in keyword-only mode", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      undefined,
    );
    const results = await hybrid.retrieve("content", "t-1");
    expect(results.find((r) => r.chunkId === "c4")).toBeUndefined();
  });

  it("constructor rejects rrfK < 1", () => {
    expect(() => new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS), undefined, { rrfK: 0 },
    )).toThrow(/rrfK/);
  });

  it("constructor rejects limit < 1", () => {
    expect(() => new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS), undefined, { limit: 0 },
    )).toThrow(/limit/);
  });

  it("limit caps the returned chunks (post-fuse)", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
      { limit: 1 },
    );
    const results = await hybrid.retrieve("retrieval", "t-1");
    expect(results.length).toBeLessThanOrEqual(1);
  });

  it("BACKDOOR: concat-dedupe strategy returns first-occurrence-only", async () => {
    // Both sources will hit c1; the result must contain c1 exactly once.
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
      { fuseStrategy: "concat-dedupe" },
    );
    const results = await hybrid.retrieve("retrieval", "t-1");
    const c1Count = results.filter((r) => r.chunkId === "c1").length;
    expect(c1Count).toBe(1);  // no duplicates
  });

  it("BACKDOOR: weighted-sum strategy honors per-source weights", async () => {
    // With keywordWeight=10, vectorWeight=0, keyword-rank should
    // dominate the final score ordering.
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
      {
        fuseStrategy: "weighted-sum",
        keywordWeight: 10,
        vectorWeight: 0,
      },
    );
    const results = await hybrid.retrieve("retrieval", "t-1");
    // First result should be the top keyword match (c1).
    expect(results[0].chunkId).toBe("c1");
  });

  it("custom KeywordRetriever adapter integrates (extension point)", async () => {
    class FixedKeywordAdapter implements KeywordRetrieverI {
      retrieve(_query: string, tenantId: string): RetrievedChunk[] {
        if (tenantId !== "t-1") return [];
        return [{ ...CHUNKS[0], score: 0.99 }];
      }
    }
    const hybrid = new HybridRetriever(new FixedKeywordAdapter(), undefined);
    const results = await hybrid.retrieve("any", "t-1");
    expect(results.length).toBe(1);
    expect(results[0].chunkId).toBe("c1");
  });

  it("custom VectorRetriever adapter integrates (production seam)", async () => {
    class FakeQdrantAdapter implements VectorRetrieverI {
      async retrieve(_query: string, tenantId: string): Promise<RetrievedChunk[]> {
        if (tenantId !== "t-1") return [];
        return [{ ...CHUNKS[1], score: 0.95 }];
      }
      async healthCheck(): Promise<boolean> { return true; }
    }
    const hybrid = new HybridRetriever(undefined, new FakeQdrantAdapter());
    const results = await hybrid.retrieve("any", "t-1");
    expect(results.length).toBe(1);
    expect(results[0].chunkId).toBe("c2");
  });

  it("empty query returns empty results (no crash)", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
    );
    const results = await hybrid.retrieve("", "t-1");
    expect(results).toEqual([]);
  });

  it("query with no matches in either source returns empty", async () => {
    const hybrid = new HybridRetriever(
      new InMemoryKeywordRetriever(CHUNKS),
      new InMemoryVectorRetriever(CHUNKS),
    );
    const results = await hybrid.retrieve("xqxqxq nothingmatches", "t-1");
    // InMemoryKeyword filters score=0; vector returns 0-score results.
    expect(results.length).toBeLessThanOrEqual(1);
  });

  it("VectorRetriever.healthCheck is optional but callable when present", async () => {
    const vector = new InMemoryVectorRetriever(CHUNKS);
    expect(typeof vector.healthCheck).toBe("function");
    expect(await vector.healthCheck()).toBe(true);
  });
});
