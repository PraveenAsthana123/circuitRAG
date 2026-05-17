// Negative drills for Iter 21 (2026-05-17): real span-level citation
// verification. Pre-fix CitationValidator ignored the answer text
// entirely and returned every retrieved chunk's id formatted as a
// "citation" — making hallucination invisible.

import { describe, it, expect } from "vitest";
import { CitationValidator } from "./citation-validator";
import { RetrievedChunk } from "./types";

function chunk(documentId: string, chunkId: string, text = "stub"): RetrievedChunk {
  return {
    chunkId,
    documentId,
    tenantId: "t",
    text,
    metadata: {},
    score: 1,
  };
}

const v = new CitationValidator();

describe("CitationValidator — span verification (P0)", () => {
  it("BACKDOOR CHECK: answer with NO citation markers returns empty cited", () => {
    // Pre-fix this returned ['doc-A#c1','doc-B#c2'] regardless of answer.
    const result = v.validate(
      "Plain answer text without any citation marker.",
      [chunk("doc-A", "c1"), chunk("doc-B", "c2")],
    );
    expect(result.cited).toEqual([]);
    expect(result.unreferenced.length).toBe(2);
    expect(result.hallucinationFlag).toBe(false); // nothing claimed → nothing uncited
  });

  it("answer with compound [doc:chunk] markers → cited matches retrieval", () => {
    const result = v.validate(
      "TypeScript is a typed superset [doc-A:c1]. It compiles to JS [doc-B:c2].",
      [chunk("doc-A", "c1"), chunk("doc-B", "c2")],
    );
    expect(result.cited.sort()).toEqual(["doc-A#c1", "doc-B#c2"]);
    expect(result.uncited).toEqual([]);
    expect(result.unreferenced).toEqual([]);
    expect(result.hallucinationFlag).toBe(false);
  });

  it("BACKDOOR CHECK: answer cites a chunk NOT in retrieval → hallucinationFlag", () => {
    const result = v.validate(
      "Per evidence [doc-A:c1] and per imaginary source [doc-PHANTOM:fake], ...",
      [chunk("doc-A", "c1")],
    );
    expect(result.cited).toEqual(["doc-A#c1"]);
    expect(result.uncited).toContain("[doc-PHANTOM:fake]");
    expect(result.hallucinationFlag).toBe(true);
  });

  it("numbered [^N] markers resolve to retrieval-order index", () => {
    const result = v.validate(
      "First evidence [^1]; second evidence [^2]; out-of-range [^99].",
      [chunk("doc-A", "c1"), chunk("doc-B", "c2")],
    );
    expect(result.cited.sort()).toEqual(["doc-A#c1", "doc-B#c2"]);
    expect(result.uncited).toEqual(["[^99]"]);
    expect(result.hallucinationFlag).toBe(true);
  });

  it("retrieved chunks never cited surface as unreferenced", () => {
    const result = v.validate(
      "Only cites the first [doc-A:c1].",
      [chunk("doc-A", "c1"), chunk("doc-B", "c2"), chunk("doc-C", "c3")],
    );
    expect(result.cited).toEqual(["doc-A#c1"]);
    expect(result.unreferenced.sort()).toEqual(["doc-B#c2", "doc-C#c3"]);
  });

  it("dedupes when same chunk cited multiple times", () => {
    const result = v.validate(
      "[doc-A:c1] ... [doc-A:c1] ... [doc-A:c1]",
      [chunk("doc-A", "c1")],
    );
    expect(result.cited).toEqual(["doc-A#c1"]);
  });
});
