// ✅ P1 IMPROVED (Iter 41, 2026-05-17): rerank now uses
//     query-term-coverage + early-position boost + verbatim-phrase
//     match instead of "+3 if substring". Pre-fix the only signal
//     was "does the chunk contain the entire query as a substring?"
//     — almost never true for natural-language queries, so the
//     reranker was effectively a no-op.
//
//     The new signals (heuristic; real production uses a cross-
//     encoder model):
//       - query_coverage: fraction of query content-words present
//         in the chunk
//       - position_boost: matched terms in the first half of the
//         chunk score higher (relevance bias)
//       - phrase_bonus: contiguous matches of >=2 query words
//
//     Real production hands off to a cross-encoder (bge-reranker-large,
//     Cohere rerank, etc.). This stub closes the "no-op reranker"
//     gap.

import { RetrievedChunk } from "./types";

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "if", "then", "is", "are",
  "was", "were", "of", "in", "on", "at", "to", "from", "by", "for",
  "with", "as", "i", "you", "he", "she", "it", "we", "they", "this",
  "that", "these", "those", "be", "been",
]);

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((t) => t.length > 0);
}

function contentTokens(text: string): string[] {
  return tokenize(text).filter((t) => !STOPWORDS.has(t));
}

export interface RerankerConfig {
  coverageWeight: number;     // 0..1
  positionWeight: number;     // 0..1
  phraseWeight: number;       // 0..1
}

const DEFAULT_CONFIG: RerankerConfig = {
  coverageWeight: 2.0,
  positionWeight: 1.0,
  phraseWeight: 1.5,
};

export class Reranker {
  constructor(private readonly config: RerankerConfig = DEFAULT_CONFIG) {}

  rerank(query: string, chunks: RetrievedChunk[]): RetrievedChunk[] {
    const queryContentTokens = contentTokens(query);
    if (queryContentTokens.length === 0) {
      return [...chunks].sort((a, b) => b.score - a.score);
    }

    return chunks
      .map((chunk) => {
        const boost = this.computeBoost(chunk.text, queryContentTokens);
        return { ...chunk, score: chunk.score + boost };
      })
      .sort((a, b) => b.score - a.score);
  }

  /** Public for testing. */
  computeBoost(chunkText: string, queryContentTokens: string[]): number {
    const cfg = this.config;
    const chunkTokens = tokenize(chunkText);
    if (chunkTokens.length === 0) return 0;
    const halfLen = Math.floor(chunkTokens.length / 2);
    const earlyTokens = new Set(chunkTokens.slice(0, halfLen || 1));
    const chunkSet = new Set(chunkTokens);

    // 1. Coverage — fraction of query content-words present.
    const present = queryContentTokens.filter((t) => chunkSet.has(t));
    const coverage = present.length / queryContentTokens.length;

    // 2. Position bias — what fraction of present-tokens are in the
    //    first half of the chunk?
    const earlyPresent = present.filter((t) => earlyTokens.has(t)).length;
    const positionBias = present.length === 0
      ? 0
      : earlyPresent / present.length;

    // 3. Phrase bonus — contiguous match of N>=2 consecutive query
    //    tokens anywhere in the chunk.
    const phraseLen = this.longestContiguousMatch(chunkTokens, queryContentTokens);
    const phraseScore = phraseLen >= 2
      ? phraseLen / queryContentTokens.length
      : 0;

    return (
      cfg.coverageWeight * coverage +
      cfg.positionWeight * positionBias +
      cfg.phraseWeight * phraseScore
    );
  }

  private longestContiguousMatch(
    chunkTokens: string[],
    queryTokens: string[],
  ): number {
    // Look for the longest prefix of queryTokens that appears
    // contiguously anywhere in chunkTokens.
    let best = 0;
    for (let i = 0; i <= chunkTokens.length - 1; i++) {
      let k = 0;
      while (
        k < queryTokens.length &&
        i + k < chunkTokens.length &&
        chunkTokens[i + k] === queryTokens[k]
      ) {
        k++;
      }
      if (k > best) best = k;
    }
    return best;
  }
}
