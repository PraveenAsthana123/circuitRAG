import { RetrievedChunk } from "./types";

export class QualityScorer {
  score(answer: string, chunks: RetrievedChunk[], grounded: boolean): number {
    let score = 0;

    if (answer.length > 50) score += 25;
    if (chunks.length >= 2) score += 25;
    if (grounded) score += 40;

    const avgRetrievalScore =
      chunks.reduce((sum, c) => sum + c.score, 0) / Math.max(chunks.length, 1);

    score += Math.min(avgRetrievalScore * 2, 10);

    return Math.min(score, 100);
  }
}
