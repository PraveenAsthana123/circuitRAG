import { RetrievedChunk } from "./types";

export class GroundingChecker {
  check(answer: string, chunks: RetrievedChunk[]): boolean {
    const evidenceText = chunks.map((c) => c.text.toLowerCase()).join(" ");
    const answerTerms = answer.toLowerCase().split(/\s+/);

    const supportedTerms = answerTerms.filter((term) =>
      evidenceText.includes(term)
    );

    return supportedTerms.length / Math.max(answerTerms.length, 1) > 0.45;
  }
}
