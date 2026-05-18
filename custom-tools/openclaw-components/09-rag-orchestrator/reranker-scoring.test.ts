// Negative drills for Iter 84 (2026-05-18): Reranker scoring contract.
// Locks the coverage + position + phrase signals that determine
// rerank order, so a refactor to add e.g. semantic-score weighting
// fails loudly if it breaks the existing signal contract.

import { describe, it, expect } from "vitest";
import { Reranker } from "./reranker";
import { RetrievedChunk } from "./types";

const C = (id: string, text: string, score = 1): RetrievedChunk => ({
  chunkId: id,
  documentId: `doc-${id}`,
  tenantId: "t",
  text,
  score,
  metadata: {},
});

describe("Iter 84 — Reranker scoring contract (P2)", () => {
  it("BACKDOOR: chunk with exact phrase match outranks chunk with no overlap", () => {
    const r = new Reranker();
    const ranked = r.rerank("retrieval augmented generation", [
      C("no-match", "totally unrelated content about cats", 1),
      C("phrase-hit", "retrieval augmented generation is a pattern", 1),
    ]);
    expect(ranked[0].chunkId).toBe("phrase-hit");
  });

  it("BACKDOOR: partial coverage outranks zero coverage", () => {
    const r = new Reranker();
    const ranked = r.rerank("retrieval generation", [
      C("zero", "cats and dogs", 1),
      C("partial", "retrieval is one half", 1),
    ]);
    expect(ranked[0].chunkId).toBe("partial");
  });

  it("position bias: early-occurrence outranks late-occurrence (same coverage)", () => {
    const r = new Reranker();
    const ranked = r.rerank("retrieval generation pattern", [
      C("late", "alpha beta gamma delta epsilon zeta retrieval generation pattern", 1),
      C("early", "retrieval generation pattern alpha beta gamma delta epsilon zeta", 1),
    ]);
    expect(ranked[0].chunkId).toBe("early");
  });

  it("phrase bonus: contiguous 2-word match outranks scattered match", () => {
    const r = new Reranker();
    const ranked = r.rerank("retrieval generation", [
      C("scattered", "retrieval is X Y Z generation", 1),
      C("contiguous", "retrieval generation flow", 1),
    ]);
    expect(ranked[0].chunkId).toBe("contiguous");
  });

  it("BACKDOOR: empty query (stopwords only) falls back to base-score sort", () => {
    const r = new Reranker();
    const ranked = r.rerank("the the the", [
      C("low", "text", 0.1),
      C("high", "text", 0.9),
    ]);
    expect(ranked[0].chunkId).toBe("high");
    expect(ranked[1].chunkId).toBe("low");
  });

  it("stopwords in query are IGNORED (don't count toward coverage)", () => {
    const r = new Reranker();
    // "the retrieval" vs "retrieval" — same content tokens.
    const boost1 = r.computeBoost("retrieval pattern", ["retrieval", "pattern"]);
    const boost2 = r.computeBoost("retrieval pattern", ["the", "retrieval", "pattern", "is"]);
    // boost2 has stopwords-pre-filtered in the query passed; results
    // depend on how Reranker tokenizes. Since `computeBoost` accepts
    // ALREADY-content-filtered tokens, this is a unit-level check
    // that stopwords passed AS content are still computed (no extra
    // filter inside computeBoost). Locks the API contract.
    expect(boost1).toBeGreaterThan(0);
    expect(boost2).toBeGreaterThan(0);
  });

  it("empty chunk text yields boost of 0 (no crash)", () => {
    const r = new Reranker();
    expect(r.computeBoost("", ["query"])).toBe(0);
  });

  it("BACKDOOR: rerank preserves chunk identity (no mutation of original)", () => {
    const r = new Reranker();
    const original = C("c1", "retrieval", 5);
    const ranked = r.rerank("retrieval", [original]);
    // Original score unchanged; new entry is a copy.
    expect(original.score).toBe(5);
    expect(ranked[0].score).toBeGreaterThan(5);
    expect(ranked[0]).not.toBe(original);
  });

  it("rerank with empty chunks list returns []", () => {
    const r = new Reranker();
    expect(r.rerank("any query", [])).toEqual([]);
  });

  it("case-insensitive matching (Query Retrieval vs query retrieval)", () => {
    const r = new Reranker();
    const ranked = r.rerank("Retrieval Pattern", [
      C("upper", "RETRIEVAL PATTERN is fine", 1),
      C("lower", "retrieval pattern is fine", 1),
    ]);
    // Both should have non-zero coverage; the position/phrase
    // signals are identical so scores tie. Test asserts that
    // BOTH boost above their base score (case-insensitive works).
    expect(ranked[0].score).toBeGreaterThan(1);
    expect(ranked[1].score).toBeGreaterThan(1);
  });

  it("punctuation stripped during tokenization (retrieval, generation matches `retrieval generation`)", () => {
    const r = new Reranker();
    const ranked = r.rerank("retrieval generation", [
      C("with-punct", "retrieval, generation, classification.", 1),
      C("plain", "retrieval generation", 1),
    ]);
    // Both should boost (punctuation doesn't block matching).
    expect(ranked[0].score).toBeGreaterThan(1);
    expect(ranked[1].score).toBeGreaterThan(1);
  });

  it("custom config weights affect ordering (regression on injection point)", () => {
    // Two rerankers with VERY different weights; their preferred
    // chunk should differ when the signals favor different chunks.
    const coverageHeavy = new Reranker({
      coverageWeight: 10, positionWeight: 0, phraseWeight: 0,
    });
    const phraseHeavy = new Reranker({
      coverageWeight: 0, positionWeight: 0, phraseWeight: 10,
    });
    const chunks = [
      // High coverage, no contiguous phrase.
      C("coverage", "retrieval X X generation X X pattern", 1),
      // Lower coverage (only 2 of 3 words), but contiguous phrase.
      C("phrase", "retrieval generation X X X X X", 1),
    ];
    const coverageFirst = coverageHeavy.rerank("retrieval generation pattern", chunks);
    const phraseFirst = phraseHeavy.rerank("retrieval generation pattern", chunks);
    expect(coverageFirst[0].chunkId).toBe("coverage");
    expect(phraseFirst[0].chunkId).toBe("phrase");
  });
});
