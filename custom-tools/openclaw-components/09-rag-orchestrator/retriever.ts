import { Chunk, RetrievedChunk } from "./types";

export class Retriever {
  constructor(private readonly chunks: Chunk[]) {}

  retrieve(query: string, tenantId: string, topK = 5): RetrievedChunk[] {
    const queryTerms = query.toLowerCase().split(/\s+/);

    return this.chunks
      .filter((c) => c.tenantId === tenantId)
      .map((chunk) => {
        const text = chunk.text.toLowerCase();

        const score = queryTerms.reduce((sum, term) => {
          return sum + (text.includes(term) ? 1 : 0);
        }, 0);

        return { ...chunk, score };
      })
      .filter((c) => c.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }
}
