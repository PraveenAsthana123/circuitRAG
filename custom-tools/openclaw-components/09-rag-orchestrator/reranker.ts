import { RetrievedChunk } from "./types";

export class Reranker {
  rerank(query: string, chunks: RetrievedChunk[]): RetrievedChunk[] {
    const normalizedQuery = query.toLowerCase();

    return chunks
      .map((chunk) => {
        let boost = 0;

        if (chunk.text.toLowerCase().includes(normalizedQuery)) {
          boost += 3;
        }

        return {
          ...chunk,
          score: chunk.score + boost,
        };
      })
      .sort((a, b) => b.score - a.score);
  }
}
