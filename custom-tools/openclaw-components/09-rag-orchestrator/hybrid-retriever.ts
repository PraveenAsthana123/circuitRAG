// Iter 114 (2026-05-18): hybrid retriever interface split.
//
// Per Agentic Plan §"RAG Productionization" + CLAUDE.md §45 (RAG
// platform patterns) §39 (hybrid retrieval = vector + keyword +
// reranker): the existing Retriever is a single in-memory BM25.
// Production needs separate keyword + vector + hybrid-ranker
// interfaces so adapters (Qdrant, pgvector, OpenSearch) can plug
// in without rewriting the orchestrator.
//
// This iter defines the THREE interfaces + an in-memory
// HybridRetriever composition + the drill. Production adapters
// implement KeywordRetrieverI / VectorRetrieverI and the existing
// Reranker (iter 84-drilled) handles re-scoring.

import { RetrievedChunk, Chunk } from "./types";

/**
 * Tenant-scoped keyword retriever (BM25 / sparse). Maps query
 * tokens to chunks via term-frequency math. Fast, no embeddings,
 * good for exact-match recall.
 */
export interface KeywordRetrieverI {
  /** Retrieve up to `limit` chunks for `query` within `tenantId`.
   *  Tenant isolation is the adapter's responsibility — wrong-
   *  tenant queries MUST return []. */
  retrieve(query: string, tenantId: string, limit?: number): RetrievedChunk[];
}

/**
 * Tenant-scoped vector retriever (semantic / dense). Maps query
 * embedding to chunks via cosine/dot-product similarity. Captures
 * semantic intent that keyword can't.
 */
export interface VectorRetrieverI {
  /** Retrieve up to `limit` chunks for `query` within `tenantId`.
   *  Adapter computes the query embedding internally (caller
   *  passes the text query, NOT the embedding — keeps the interface
   *  agnostic to embedding model swaps). */
  retrieve(query: string, tenantId: string, limit?: number): Promise<RetrievedChunk[]>;
  /** Health check for the vector backend (Qdrant/pgvector ping). */
  healthCheck?(): Promise<boolean>;
}

/**
 * Fuse strategy for combining keyword + vector results before the
 * (separate) reranker pass. RRF (reciprocal-rank-fusion) is the
 * canonical default — combines two ranked lists by 1/(k + rank).
 */
export type FuseStrategy = "rrf" | "concat-dedupe" | "weighted-sum";

export interface HybridRetrieverOptions {
  /** RRF "k" constant (default 60, per RRF paper). */
  rrfK?: number;
  /** Per-source weight for weighted-sum strategy. */
  keywordWeight?: number;
  vectorWeight?: number;
  /** Fuse strategy (default "rrf"). */
  fuseStrategy?: FuseStrategy;
  /** Max chunks returned post-fuse (default 20). */
  limit?: number;
}

/**
 * Combines keyword + vector retrieval into one ranked list.
 * Production calls hybrid → reranker (iter 84) → orchestrator.
 *
 * Either source can be omitted at construction — then the hybrid
 * degenerates to "keyword only" or "vector only" (with the FuseStrategy
 * still applied but trivially). Useful for failover modes:
 *   keyword=in-memory BM25 (always available)
 *   vector=Qdrant (might be unhealthy → omit at runtime, fall back)
 */
export class HybridRetriever {
  private readonly rrfK: number;
  private readonly keywordWeight: number;
  private readonly vectorWeight: number;
  private readonly fuseStrategy: FuseStrategy;
  private readonly limit: number;

  constructor(
    private readonly keyword?: KeywordRetrieverI,
    private readonly vector?: VectorRetrieverI,
    opts: HybridRetrieverOptions = {},
  ) {
    if (!keyword && !vector) {
      throw new Error("HybridRetriever requires at least one of {keyword, vector}");
    }
    this.rrfK = opts.rrfK ?? 60;
    this.keywordWeight = opts.keywordWeight ?? 0.5;
    this.vectorWeight = opts.vectorWeight ?? 0.5;
    this.fuseStrategy = opts.fuseStrategy ?? "rrf";
    this.limit = opts.limit ?? 20;
    if (this.rrfK < 1) throw new Error("rrfK must be >= 1");
    if (this.limit < 1) throw new Error("limit must be >= 1");
  }

  async retrieve(query: string, tenantId: string): Promise<RetrievedChunk[]> {
    const keywordResults = this.keyword
      ? this.keyword.retrieve(query, tenantId, this.limit)
      : [];
    const vectorResults = this.vector
      ? await this.vector.retrieve(query, tenantId, this.limit)
      : [];

    const fused = this.fuse(keywordResults, vectorResults);
    return fused.slice(0, this.limit);
  }

  private fuse(
    keyword: RetrievedChunk[],
    vector: RetrievedChunk[],
  ): RetrievedChunk[] {
    switch (this.fuseStrategy) {
      case "rrf":
        return this.fuseRRF(keyword, vector);
      case "concat-dedupe":
        return this.fuseConcatDedupe(keyword, vector);
      case "weighted-sum":
        return this.fuseWeightedSum(keyword, vector);
    }
  }

  /**
   * Reciprocal-rank fusion. For each chunk, score = sum over
   * sources of 1 / (rrfK + rank). Higher = better. The canonical
   * fusion for hybrid search per the 2009 RRF paper.
   */
  private fuseRRF(
    keyword: RetrievedChunk[],
    vector: RetrievedChunk[],
  ): RetrievedChunk[] {
    const scoreMap = new Map<string, { chunk: RetrievedChunk; score: number }>();
    const accumulate = (list: RetrievedChunk[]) => {
      list.forEach((chunk, rank) => {
        const rrfContribution = 1 / (this.rrfK + rank + 1);
        const existing = scoreMap.get(chunk.chunkId);
        if (existing) {
          existing.score += rrfContribution;
        } else {
          scoreMap.set(chunk.chunkId, { chunk, score: rrfContribution });
        }
      });
    };
    accumulate(keyword);
    accumulate(vector);
    return Array.from(scoreMap.values())
      .sort((a, b) => b.score - a.score)
      .map((entry) => ({ ...entry.chunk, score: entry.score }));
  }

  /**
   * Concat then dedupe by chunkId, preserving first-occurrence
   * order. Cheap; useful when source ranking quality is asymmetric
   * and you want one to dominate.
   */
  private fuseConcatDedupe(
    keyword: RetrievedChunk[],
    vector: RetrievedChunk[],
  ): RetrievedChunk[] {
    const seen = new Set<string>();
    const out: RetrievedChunk[] = [];
    for (const chunk of [...keyword, ...vector]) {
      if (seen.has(chunk.chunkId)) continue;
      seen.add(chunk.chunkId);
      out.push(chunk);
    }
    return out;
  }

  /**
   * Weighted-sum of native scores. Caller must ensure scores are
   * already on comparable scales (or accept the bias).
   */
  private fuseWeightedSum(
    keyword: RetrievedChunk[],
    vector: RetrievedChunk[],
  ): RetrievedChunk[] {
    const scoreMap = new Map<string, { chunk: RetrievedChunk; score: number }>();
    for (const chunk of keyword) {
      scoreMap.set(chunk.chunkId, {
        chunk,
        score: (scoreMap.get(chunk.chunkId)?.score ?? 0) + chunk.score * this.keywordWeight,
      });
    }
    for (const chunk of vector) {
      const existing = scoreMap.get(chunk.chunkId);
      if (existing) {
        existing.score += chunk.score * this.vectorWeight;
      } else {
        scoreMap.set(chunk.chunkId, {
          chunk,
          score: chunk.score * this.vectorWeight,
        });
      }
    }
    return Array.from(scoreMap.values())
      .sort((a, b) => b.score - a.score)
      .map((entry) => ({ ...entry.chunk, score: entry.score }));
  }
}

/**
 * Helper to build a deterministic in-memory KeywordRetrieverI
 * adapter from a fixed chunk corpus. Useful for unit tests +
 * a default for dev mode. Production is a real BM25 service.
 */
export class InMemoryKeywordRetriever implements KeywordRetrieverI {
  constructor(private readonly chunks: Chunk[]) {}
  retrieve(query: string, tenantId: string, limit = 10): RetrievedChunk[] {
    const queryTokens = tokenize(query);
    if (queryTokens.length === 0) return [];
    return this.chunks
      .filter((c) => c.tenantId === tenantId)
      .map((c) => {
        const chunkTokens = tokenize(c.text);
        const matches = queryTokens.filter((t) => chunkTokens.includes(t)).length;
        const score = matches / queryTokens.length;
        return { ...c, score };
      })
      .filter((c) => c.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }
}

/**
 * Stub in-memory VectorRetriever for tests. Uses character-trigram
 * overlap as a stand-in for semantic similarity — not for production.
 */
export class InMemoryVectorRetriever implements VectorRetrieverI {
  constructor(private readonly chunks: Chunk[]) {}
  async retrieve(query: string, tenantId: string, limit = 10): Promise<RetrievedChunk[]> {
    const qTrigrams = trigrams(query.toLowerCase());
    if (qTrigrams.size === 0) return [];
    return this.chunks
      .filter((c) => c.tenantId === tenantId)
      .map((c) => {
        const cTrigrams = trigrams(c.text.toLowerCase());
        const intersection = new Set([...qTrigrams].filter((g) => cTrigrams.has(g)));
        const union = new Set([...qTrigrams, ...cTrigrams]);
        const score = union.size === 0 ? 0 : intersection.size / union.size;
        return { ...c, score };
      })
      .filter((c) => c.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }
  async healthCheck(): Promise<boolean> { return true; }
}

function tokenize(s: string): string[] {
  return s.toLowerCase().split(/\W+/).filter((t) => t.length > 0);
}

function trigrams(s: string): Set<string> {
  const out = new Set<string>();
  for (let i = 0; i < s.length - 2; i++) out.add(s.slice(i, i + 3));
  return out;
}
