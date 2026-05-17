// Negative drills for Iter 41 (2026-05-17): Reranker improvements.

import { describe, it, expect } from "vitest";
import { Reranker } from "./reranker";
import { RetrievedChunk } from "./types";

function chunk(text: string, baseScore = 1, id = "c"): RetrievedChunk {
  return {
    chunkId: id, documentId: "d", tenantId: "t",
    text, metadata: {}, score: baseScore,
  };
}

const r = new Reranker();

describe("Reranker — query coverage + position + phrase (P1)", () => {
  it("BACKDOOR CHECK: chunks that share query terms outrank chunks that don't", () => {
    // Pre-fix: only the full-substring match gave a boost. Neither
    // chunk contained the whole query, so both got +0 → ranked by
    // initial score only. With BM25-comparable base scores, the
    // boost now drives ordering.
    const chunks = [
      chunk("Memory architecture in distributed systems", 1, "a"),
      chunk("Cooking recipes for tomato soup", 1, "b"),
    ];
    const out = r.rerank("How does distributed memory work?", chunks);
    expect(out[0].chunkId).toBe("a");
    expect(out[0].score).toBeGreaterThan(out[1].score);
  });

  it("verbatim phrase match scores higher than scattered terms", () => {
    const chunks = [
      chunk("distributed memory consistency", 1, "phrase"),
      chunk("memory is used in distributed contexts", 1, "scattered"),
    ];
    const out = r.rerank("distributed memory", chunks);
    expect(out[0].chunkId).toBe("phrase");
  });

  it("early-position match scores higher than late match", () => {
    const filler = Array(50).fill("filler").join(" ");
    const chunks = [
      chunk("TypeScript ${filler}".replace("${filler}", filler), 1, "early"),
      chunk(`${filler} TypeScript`, 1, "late"),
    ];
    const out = r.rerank("TypeScript", chunks);
    expect(out[0].chunkId).toBe("early");
  });

  it("empty query content (all stopwords) leaves ordering unchanged", () => {
    const chunks = [
      chunk("anything goes", 1, "a"),
      chunk("everything fine", 3, "b"),
    ];
    const out = r.rerank("the and of", chunks);
    expect(out[0].chunkId).toBe("b");
  });

  it("computeBoost is monotonic in coverage", () => {
    const r = new Reranker();
    const partial = r.computeBoost(
      "TypeScript", ["TypeScript", "compiler"],
    );
    const full = r.computeBoost(
      "TypeScript compiler", ["TypeScript", "compiler"],
    );
    expect(full).toBeGreaterThan(partial);
  });

  it("custom config can disable position bias", () => {
    const noPos = new Reranker({ coverageWeight: 1, positionWeight: 0, phraseWeight: 1 });
    const filler = Array(20).fill("filler").join(" ");
    const chunks = [
      chunk(`TypeScript ${filler}`, 1, "early"),
      chunk(`${filler} TypeScript`, 1, "late"),
    ];
    const out = noPos.rerank("TypeScript", chunks);
    // With position weight 0 the two chunks score identically;
    // sort is stable on tie so original order preserved.
    expect(out[0].score).toBe(out[1].score);
  });
});
