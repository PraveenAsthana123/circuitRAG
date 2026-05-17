// Negative drills for Iter 38 (2026-05-17): BM25 retrieval scoring.

import { describe, it, expect } from "vitest";
import { Retriever } from "./retriever";
import { Chunk } from "./types";

function chunk(id: string, text: string, tenantId = "t"): Chunk {
  return { chunkId: id, documentId: "d", tenantId, text, metadata: {} };
}

describe("Retriever — BM25 (P0)", () => {
  it("BACKDOOR CHECK: a rare term scores higher than a common term", () => {
    // 'TypeScript' appears in 1/3 chunks; 'is' appears in 3/3.
    // Pre-fix: both scored 1.0 (term-in-text-or-not).
    // BM25: rare term has higher IDF, so the chunk containing
    // 'TypeScript' must beat chunks that only match on 'is'.
    const r = new Retriever([
      chunk("a", "TypeScript is a typed language"),
      chunk("b", "Python is a dynamic language"),
      chunk("c", "Rust is a memory-safe language"),
    ]);
    const top = r.retrieve("TypeScript is", "t", 3);
    expect(top[0].chunkId).toBe("a");
    // 'b' and 'c' should appear but with lower scores than 'a'.
    expect(top[0].score).toBeGreaterThan(top[1].score);
  });

  it("BACKDOOR CHECK: short chunks aren't unfairly penalized vs long ones", () => {
    // Pre-fix: a 1000-word chunk and a 5-word chunk with the same
    // term scored identically. BM25 normalizes by length so the
    // short, on-topic chunk wins.
    const r = new Retriever([
      chunk("short", "TypeScript is great"),
      chunk(
        "long",
        ("filler ".repeat(500) + " TypeScript is sometimes mentioned " +
         " filler".repeat(500)).trim(),
      ),
    ]);
    const top = r.retrieve("TypeScript", "t");
    expect(top[0].chunkId).toBe("short");
  });

  it("term-frequency saturates (50 repeats != 50× the score)", () => {
    const r = new Retriever([
      chunk("once", "TypeScript and other languages"),
      chunk("repeated", Array(50).fill("TypeScript").join(" ")),
    ]);
    const top = r.retrieve("TypeScript", "t");
    // The repeated chunk does score higher (more density) but not
    // 50× — saturation kicks in.
    const ratio = top[0].score / top[1].score;
    expect(ratio).toBeLessThan(10);
  });

  it("tenant filter still works", () => {
    const r = new Retriever([
      chunk("a", "TypeScript is great", "tenant-A"),
      chunk("b", "TypeScript is great", "tenant-B"),
    ]);
    const aRes = r.retrieve("TypeScript", "tenant-A");
    expect(aRes.length).toBe(1);
    expect(aRes[0].chunkId).toBe("a");
  });

  it("no-match query returns empty", () => {
    const r = new Retriever([chunk("a", "TypeScript is great")]);
    expect(r.retrieve("Quantum chromodynamics", "t")).toEqual([]);
  });

  it("topK caps result count", () => {
    const r = new Retriever([
      chunk("a", "TypeScript"),
      chunk("b", "TypeScript"),
      chunk("c", "TypeScript"),
      chunk("d", "TypeScript"),
    ]);
    expect(r.retrieve("TypeScript", "t", 2).length).toBe(2);
  });

  it("empty index returns empty", () => {
    const r = new Retriever([]);
    expect(r.retrieve("anything", "t")).toEqual([]);
  });

  it("punctuation and case don't break matching", () => {
    const r = new Retriever([
      chunk("a", "TypeScript, JavaScript, and CoffeeScript"),
    ]);
    expect(r.retrieve("javascript", "t")[0].chunkId).toBe("a");
    expect(r.retrieve("CoffeeScript", "t")[0].chunkId).toBe("a");
  });
});
