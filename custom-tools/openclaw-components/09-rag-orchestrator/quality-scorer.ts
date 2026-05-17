// ✅ P2 IMPROVED (Iter 34, 2026-05-17): magic numbers (25/25/40/10)
//     moved to a tunable QualityScorerConfig. Pre-fix the weights
//     were hardcoded so:
//       - a different domain couldn't reweight (e.g., medical RAG
//         needs grounding > everything else)
//       - the values were untunable against a golden eval set
//       - the score returned was opaque ("we got 69 — why?")
//
//     Now the weights are explicit, validated to sum ≤ 100, and the
//     scorer returns a breakdown alongside the total so callers can
//     diagnose which dimension drove a low score.

import { RetrievedChunk } from "./types";

export interface QualityScorerConfig {
  /** Points awarded if answer.length > minAnswerLength. */
  lengthWeight: number;
  minAnswerLength: number;
  /** Points awarded if chunks.length >= minChunkCount. */
  chunkCountWeight: number;
  minChunkCount: number;
  /** Points awarded if grounded === true. */
  groundedWeight: number;
  /** Multiplier on average retrieval score (capped at retrievalCap). */
  retrievalMultiplier: number;
  retrievalCap: number;
}

export const DEFAULT_QUALITY_CONFIG: QualityScorerConfig = {
  lengthWeight: 25,
  minAnswerLength: 50,
  chunkCountWeight: 25,
  minChunkCount: 2,
  groundedWeight: 40,
  retrievalMultiplier: 2,
  retrievalCap: 10,
};

export interface QualityBreakdown {
  total: number;
  length: number;
  chunkCount: number;
  grounded: number;
  retrieval: number;
}

export class QualityScorer {
  constructor(private readonly config: QualityScorerConfig = DEFAULT_QUALITY_CONFIG) {
    const sum =
      config.lengthWeight + config.chunkCountWeight +
      config.groundedWeight + config.retrievalCap;
    if (sum > 100) {
      throw new Error(
        `Quality scorer weights sum to ${sum}; max is 100`,
      );
    }
    if (
      config.lengthWeight < 0 || config.chunkCountWeight < 0 ||
      config.groundedWeight < 0 || config.retrievalCap < 0 ||
      config.retrievalMultiplier < 0 || config.minAnswerLength < 0 ||
      config.minChunkCount < 0
    ) {
      throw new Error("All quality scorer weights must be >= 0");
    }
  }

  scoreWithBreakdown(
    answer: string,
    chunks: RetrievedChunk[],
    grounded: boolean,
  ): QualityBreakdown {
    const cfg = this.config;
    const length = answer.length > cfg.minAnswerLength ? cfg.lengthWeight : 0;
    const chunkCount = chunks.length >= cfg.minChunkCount ? cfg.chunkCountWeight : 0;
    const groundedScore = grounded ? cfg.groundedWeight : 0;

    const avgRetrievalScore =
      chunks.reduce((sum, c) => sum + c.score, 0) /
      Math.max(chunks.length, 1);
    const retrieval = Math.min(
      avgRetrievalScore * cfg.retrievalMultiplier,
      cfg.retrievalCap,
    );

    const total = Math.min(length + chunkCount + groundedScore + retrieval, 100);
    return { total, length, chunkCount, grounded: groundedScore, retrieval };
  }

  /** Backcompat: pre-fix returned just the total. */
  score(answer: string, chunks: RetrievedChunk[], grounded: boolean): number {
    return this.scoreWithBreakdown(answer, chunks, grounded).total;
  }
}
