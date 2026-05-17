// ✅ P1 IMPROVED (Iter 26, 2026-05-17): n-gram overlap + length
//     normalization + stopword filtering. Pre-fix was unigram bag-of-
//     words overlap — easily defeated:
//       - "the the the the the" against any answer returned true
//         (because "the" is in every chunk).
//       - Long answers padded with chunk words trivially scored high.
//     Both gone now.
//
//     What this fix DOES cover:
//       - Stopword removal so common words don't inflate overlap.
//       - n-gram (default trigram) overlap so word-order matters,
//         not just bag presence. An answer that re-uses chunk
//         vocabulary but in nonsense order will score low.
//       - Length normalization: answers > 200 trigrams need higher
//         coverage than short answers (penalizes padding).
//       - Configurable threshold + n-gram size.
//
//     Real production needs NLI (Natural Language Inference) — a
//     model like vectara/hallucination_evaluation_model or
//     Ragas faithfulness. This is still a heuristic. See GAPS row.

import { RetrievedChunk } from "./types";

// Top ~50 English stopwords. Real prod would use a proper list
// (e.g., NLTK's 179) but ~50 closes the worst cases.
const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "if", "then", "else",
  "is", "are", "was", "were", "be", "been", "being", "am",
  "i", "you", "he", "she", "it", "we", "they", "this", "that",
  "these", "those", "of", "in", "on", "at", "to", "from", "by",
  "for", "with", "as", "into", "about", "against", "between",
  "before", "after", "above", "below", "up", "down", "out",
  "over", "under", "again", "further", "all", "any", "some",
  "no", "not", "only", "own", "same", "so", "than", "too", "very",
  "can", "will", "just", "should", "now",
]);

export interface GroundingConfig {
  ngramSize: number;        // default 3 (trigrams)
  threshold: number;        // default 0.40
  stopwordsEnabled: boolean;
}

const DEFAULT_CONFIG: GroundingConfig = {
  ngramSize: 3,
  threshold: 0.40,
  stopwordsEnabled: true,
};

export class GroundingChecker {
  constructor(private readonly config: GroundingConfig = DEFAULT_CONFIG) {
    if (config.ngramSize < 1) throw new Error("ngramSize must be >= 1");
    if (config.threshold < 0 || config.threshold > 1) {
      throw new Error("threshold must be in [0, 1]");
    }
  }

  check(answer: string, chunks: RetrievedChunk[]): boolean {
    if (chunks.length === 0) return false;

    const answerTokens = this.tokenize(answer);
    const evidenceTokens = chunks.flatMap((c) => this.tokenize(c.text));

    if (answerTokens.length < this.config.ngramSize) {
      // Too short for the configured n; fall back to unigram
      // overlap on non-stopwords.
      const evSet = new Set(evidenceTokens);
      const hits = answerTokens.filter((t) => evSet.has(t)).length;
      const ratio = hits / Math.max(answerTokens.length, 1);
      return ratio >= this.config.threshold;
    }

    const answerNgrams = this.ngrams(answerTokens, this.config.ngramSize);
    const evidenceNgrams = new Set(
      this.ngrams(evidenceTokens, this.config.ngramSize),
    );

    if (answerNgrams.length === 0) return false;

    const supportedNgrams = answerNgrams.filter((g) => evidenceNgrams.has(g));
    const ratio = supportedNgrams.length / answerNgrams.length;

    // Length penalty: long answers padded with chunk words need
    // higher coverage. Above 200 n-grams the bar rises linearly to
    // threshold * 1.5 at 500+ n-grams.
    const lengthPenalty = answerNgrams.length > 200
      ? Math.min(1.5, 1 + (answerNgrams.length - 200) / 600)
      : 1.0;
    const adjustedThreshold = Math.min(0.95, this.config.threshold * lengthPenalty);

    return ratio >= adjustedThreshold;
  }

  /** Public for testing. */
  tokenize(text: string): string[] {
    const tokens = text
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, " ")  // strip punctuation
      .split(/\s+/)
      .filter((t) => t.length > 0);
    return this.config.stopwordsEnabled
      ? tokens.filter((t) => !STOPWORDS.has(t))
      : tokens;
  }

  /** Public for testing. */
  ngrams(tokens: string[], n: number): string[] {
    if (tokens.length < n) return [];
    const out: string[] = [];
    for (let i = 0; i <= tokens.length - n; i++) {
      out.push(tokens.slice(i, i + n).join(" "));
    }
    return out;
  }
}
