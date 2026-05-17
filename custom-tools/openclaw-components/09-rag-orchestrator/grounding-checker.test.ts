// Negative drills for Iter 26 (2026-05-17): GroundingChecker
// n-gram + length-normalize.

import { describe, it, expect } from "vitest";
import { GroundingChecker } from "./grounding-checker";
import { RetrievedChunk } from "./types";

function chunk(text: string): RetrievedChunk {
  return {
    chunkId: "c", documentId: "d", tenantId: "t",
    text, metadata: {}, score: 1,
  };
}

const gc = new GroundingChecker();

describe("GroundingChecker — n-gram overlap (P1)", () => {
  it("answer that closely paraphrases the evidence is grounded", () => {
    const evidence = [chunk("TypeScript is a typed superset of JavaScript that compiles to plain JS")];
    expect(gc.check(
      "TypeScript is a typed superset of JavaScript",
      evidence,
    )).toBe(true);
  });

  it("BACKDOOR CHECK: stopword padding ('the the the') does NOT pass", () => {
    // Pre-fix: every "the" matched the evidence's "the" via bag-of-
    // words unigram, so the ratio was 1.0 → grounded. Now: stopwords
    // are removed before scoring, so the answer has 0 content tokens
    // and grounding fails.
    const evidence = [chunk("The quick brown fox jumps over the lazy dog")];
    expect(gc.check("the the the the the the the", evidence)).toBe(false);
  });

  it("BACKDOOR CHECK: reordered bag-of-words does NOT pass at trigram level", () => {
    // Pre-fix: word order didn't matter; an answer that used chunk
    // vocabulary in any order scored as grounded. Now: trigrams
    // require word adjacency, so scrambled words fail.
    const evidence = [chunk(
      "TypeScript compiles to JavaScript using the tsc compiler",
    )];
    // Same words; nonsense order. No 3-word substring appears in the
    // evidence except possibly trivial ones, so n-gram overlap is low.
    expect(gc.check(
      "compiler tsc the using JavaScript to compiles TypeScript",
      evidence,
    )).toBe(false);
  });

  it("answer with NO evidence overlap fails", () => {
    const evidence = [chunk("TypeScript is great")];
    expect(gc.check(
      "Quantum physics involves wavefunctions and superposition",
      evidence,
    )).toBe(false);
  });

  it("empty chunks → not grounded (no evidence to ground against)", () => {
    expect(gc.check("anything goes here", [])).toBe(false);
  });

  it("length penalty: very long answer needs higher coverage", () => {
    const evidence = [chunk(
      "TypeScript compiles to JavaScript using the tsc compiler from Microsoft",
    )];
    // Long answer that includes the evidence sentence verbatim once
    // plus 200 trigrams of unrelated text.
    const filler = Array(700).fill("alpha beta gamma delta epsilon zeta eta theta").join(" ");
    const longAnswer = `TypeScript compiles to JavaScript using the tsc compiler from Microsoft. ${filler}`;
    // Most of the answer is unsupported padding; ratio drops below
    // the length-penalty-adjusted threshold.
    expect(gc.check(longAnswer, evidence)).toBe(false);
  });

  it("tokenize strips punctuation + lowercases + drops stopwords", () => {
    const tokens = gc.tokenize("The Quick, brown FOX! Jumps...");
    expect(tokens).not.toContain("the");
    expect(tokens).toContain("quick");
    expect(tokens).toContain("brown");
    expect(tokens).toContain("fox");
    expect(tokens).toContain("jumps");
  });

  it("ngrams emits sliding window of length n", () => {
    expect(gc.ngrams(["a", "b", "c", "d"], 2))
      .toEqual(["a b", "b c", "c d"]);
    expect(gc.ngrams(["a", "b"], 3)).toEqual([]);
  });

  it("configurable threshold lets a strict caller require near-perfect overlap", () => {
    const strict = new GroundingChecker({
      ngramSize: 3, threshold: 0.95, stopwordsEnabled: true,
    });
    const evidence = [chunk("TypeScript is a typed superset of JavaScript")];
    // Partial overlap → fails strict threshold.
    expect(strict.check(
      "TypeScript is widely adopted in industry",
      evidence,
    )).toBe(false);
  });

  it("rejects invalid config", () => {
    expect(() => new GroundingChecker({
      ngramSize: 0, threshold: 0.5, stopwordsEnabled: true,
    })).toThrow();
    expect(() => new GroundingChecker({
      ngramSize: 3, threshold: 1.5, stopwordsEnabled: true,
    })).toThrow();
  });
});
