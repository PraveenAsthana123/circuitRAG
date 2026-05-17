// Negative drills for Iter 34 (2026-05-17): QualityScorer config.

import { describe, it, expect } from "vitest";
import {
  QualityScorer,
  DEFAULT_QUALITY_CONFIG,
  QualityScorerConfig,
} from "./quality-scorer";
import { RetrievedChunk } from "./types";

function chunk(score = 1.5): RetrievedChunk {
  return {
    chunkId: "c", documentId: "d", tenantId: "t",
    text: "stub", metadata: {}, score,
  };
}

describe("QualityScorer — configurable weights (P2)", () => {
  it("backcompat: default config reproduces pre-fix scoring", () => {
    const s = new QualityScorer();
    const ans = "x".repeat(60);  // > 50 → length weight
    const total = s.score(ans, [chunk(), chunk()], true);
    // Pre-fix: 25 + 25 + 40 + min(1.5*2, 10) = 90 + 3 = 93
    expect(total).toBe(93);
  });

  it("BACKDOOR CHECK: custom config changes the total", () => {
    // Caller that cares ONLY about groundedness.
    const groundedOnly: QualityScorerConfig = {
      lengthWeight: 0, minAnswerLength: 0,
      chunkCountWeight: 0, minChunkCount: 1,
      groundedWeight: 90, retrievalMultiplier: 0, retrievalCap: 10,
    };
    const s = new QualityScorer(groundedOnly);
    expect(s.score("short", [chunk()], true)).toBe(90);
    expect(s.score("short", [chunk()], false)).toBe(0);
  });

  it("scoreWithBreakdown returns per-dimension scores for diagnosis", () => {
    const s = new QualityScorer();
    const b = s.scoreWithBreakdown(
      "x".repeat(60),
      [chunk(), chunk()],
      true,
    );
    expect(b.length).toBe(25);
    expect(b.chunkCount).toBe(25);
    expect(b.grounded).toBe(40);
    expect(b.retrieval).toBe(3);
    expect(b.total).toBe(93);
  });

  it("score caps at 100 even when weights sum higher (defensive)", () => {
    // Weights sum exactly to 100 → can return 100 max.
    const cfg = { ...DEFAULT_QUALITY_CONFIG, retrievalCap: 10 };
    const s = new QualityScorer(cfg);
    const chunks = [chunk(50), chunk(50)]; // avg=50, *2=100, cap=10
    const b = s.scoreWithBreakdown("x".repeat(60), chunks, true);
    expect(b.total).toBe(100);
  });

  it("rejects weights that sum above 100", () => {
    expect(() => new QualityScorer({
      lengthWeight: 50, minAnswerLength: 50,
      chunkCountWeight: 50, minChunkCount: 2,
      groundedWeight: 50, retrievalMultiplier: 2, retrievalCap: 50,
    })).toThrow(/sum to 200/);
  });

  it("rejects negative weights", () => {
    expect(() => new QualityScorer({
      ...DEFAULT_QUALITY_CONFIG, groundedWeight: -1,
    })).toThrow();
  });

  it("retrieval contribution is capped at retrievalCap", () => {
    const s = new QualityScorer();
    // chunk score huge — would multiply to massive without cap
    const b = s.scoreWithBreakdown(
      "x".repeat(60),
      [chunk(999)],
      false,
    );
    expect(b.retrieval).toBe(10); // capped
  });

  it("short answer gets zero length weight", () => {
    const s = new QualityScorer();
    const b = s.scoreWithBreakdown(
      "tiny", [chunk(), chunk()], true,
    );
    expect(b.length).toBe(0);
  });
});
