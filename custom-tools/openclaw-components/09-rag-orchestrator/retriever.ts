// ✅ P0 IMPROVED (Iter 38, 2026-05-17): scoring upgraded from
//     "term-in-text-or-not" to BM25 (Okapi). Pre-fix the scoring
//     function had several failure modes:
//       - A 10-word chunk and a 1000-word chunk with the same term
//         scored identically (no length normalization).
//       - A common term (in nearly every chunk) scored the same as
//         a rare term (no inverse-document-frequency weighting).
//       - Multiple occurrences of a term in a chunk didn't help.
//
//     BM25 fixes all three:
//       - Term frequency saturates (k1) so a 50× repeat doesn't
//         dominate.
//       - Length normalization (b) so short chunks aren't unfairly
//         penalized vs long ones.
//       - IDF weighting so rare terms drive the score.
//
//     Real production should hand off to a vector DB (Qdrant /
//     pgvector) for semantic + an inverted index (Elasticsearch /
//     Tantivy) for keyword. This pure-JS implementation is the
//     keyword-side proof and removes the worst failure modes; it
//     should NOT be the keyword retriever in a tier-1 system.

import { Chunk, RetrievedChunk } from "./types";

const K1 = 1.5;  // term-frequency saturation
const B = 0.75;  // length normalization

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((t) => t.length > 0);
}

export class Retriever {
  private readonly tokenized: Map<string, string[]>;
  private readonly avgDocLen: number;
  private readonly docFreq: Map<string, number>;

  constructor(private readonly chunks: Chunk[]) {
    // Pre-tokenize + index on construction so retrieve() is O(query × chunks).
    this.tokenized = new Map();
    let totalLen = 0;
    const df = new Map<string, number>();
    for (const c of chunks) {
      const tokens = tokenize(c.text);
      this.tokenized.set(c.chunkId, tokens);
      totalLen += tokens.length;
      // df counts the number of distinct chunks each term appears in.
      const seen = new Set(tokens);
      for (const t of seen) df.set(t, (df.get(t) ?? 0) + 1);
    }
    this.avgDocLen = chunks.length === 0 ? 0 : totalLen / chunks.length;
    this.docFreq = df;
  }

  retrieve(query: string, tenantId: string, topK = 5): RetrievedChunk[] {
    const queryTerms = tokenize(query);
    const N = this.chunks.length;
    if (N === 0) return [];

    return this.chunks
      .filter((c) => c.tenantId === tenantId)
      .map((chunk) => {
        const tokens = this.tokenized.get(chunk.chunkId) ?? [];
        const docLen = tokens.length;
        const tf = new Map<string, number>();
        for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);

        let score = 0;
        for (const term of queryTerms) {
          const f = tf.get(term) ?? 0;
          if (f === 0) continue;
          const df = this.docFreq.get(term) ?? 0;
          // Robertson IDF (smoothed; clamps to >0).
          const idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
          const denom = f + K1 * (1 - B + B * (docLen / (this.avgDocLen || 1)));
          score += idf * ((f * (K1 + 1)) / denom);
        }
        return { ...chunk, score };
      })
      .filter((c) => c.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }
}
