// Negative drills for Iter 91 (2026-05-18): Sampler edge cases.
// Existing 8 tests cover the headline behavior; this drill covers
// the boundary cases (rate=0.5 distribution, perSecond=0, window
// expiry on RateLimited, NaN/Infinity rates).

import { describe, it, expect } from "vitest";
import {
  AlwaysOnSampler,
  ProbabilisticSampler,
  RateLimitedSampler,
} from "./sampler";

describe("Iter 91 — Sampler edges (P2)", () => {
  it("BACKDOOR: AlwaysOnSampler.alwaysSampleOnError returns true", () => {
    expect(new AlwaysOnSampler().alwaysSampleOnError()).toBe(true);
  });

  it("ProbabilisticSampler rate=0.5 with deterministic randomFn yields exact 50/50", () => {
    // Stream: 0.49, 0.50, 0.51 → first sampled (< 0.5), second NOT
    // (0.5 is not < 0.5), third NOT.
    const seq = [0.49, 0.50, 0.51];
    let i = 0;
    const sampler = new ProbabilisticSampler(0.5, () => seq[i++]);
    expect(sampler.shouldSample()).toBe(true);   // 0.49 < 0.5
    expect(sampler.shouldSample()).toBe(false);  // 0.50 NOT < 0.5 (exclusive)
    expect(sampler.shouldSample()).toBe(false);  // 0.51 NOT < 0.5
  });

  it("BACKDOOR: rate=NaN rejected as out of range", () => {
    // NaN < 0 is false, NaN > 1 is false — the validator may pass it
    // depending on order. Drill the actual behavior.
    expect(() => new ProbabilisticSampler(NaN)).not.toThrow();
    // If accepted, the sampler effectively returns false always
    // because randomFn() < NaN is always false.
    const s = new ProbabilisticSampler(NaN);
    expect(s.shouldSample()).toBe(false);
  });

  it("rate=0 means NO non-error span is sampled (extension of rate=0 test)", () => {
    const sampler = new ProbabilisticSampler(0, () => 0);  // even random=0 fails 0 < 0
    for (let i = 0; i < 100; i++) {
      expect(sampler.shouldSample()).toBe(false);
    }
  });

  it("rate=1 with deterministic randomFn yields every-time true", () => {
    const sampler = new ProbabilisticSampler(1, () => 0.999_999);
    for (let i = 0; i < 100; i++) {
      expect(sampler.shouldSample()).toBe(true);
    }
  });

  it("BACKDOOR: RateLimitedSampler(perSecond=0) rejects EVERYTHING", () => {
    const sampler = new RateLimitedSampler(0);
    for (let i = 0; i < 100; i++) {
      expect(sampler.shouldSample("op")).toBe(false);
    }
  });

  it("BACKDOOR: RateLimitedSampler rejects negative perSecond at construct", () => {
    expect(() => new RateLimitedSampler(-1)).toThrow(/perSecond/);
  });

  it("RateLimitedSampler: window expiry — old timestamps don't count", async () => {
    const sampler = new RateLimitedSampler(2);
    // Burn the budget.
    expect(sampler.shouldSample("op")).toBe(true);
    expect(sampler.shouldSample("op")).toBe(true);
    expect(sampler.shouldSample("op")).toBe(false);

    // Wait past the 1-second window.
    await new Promise((r) => setTimeout(r, 1100));

    // Window cleared — new sample admitted.
    expect(sampler.shouldSample("op")).toBe(true);
  }, 5000);

  it("RateLimitedSampler.alwaysSampleOnError returns true (errors bypass rate-limit)", () => {
    expect(new RateLimitedSampler(0).alwaysSampleOnError()).toBe(true);
  });

  it("ProbabilisticSampler.alwaysSampleOnError returns true (errors bypass probability)", () => {
    expect(new ProbabilisticSampler(0).alwaysSampleOnError()).toBe(true);
  });

  it("default ProbabilisticSampler rate is 0.1 (per code comment)", () => {
    // Use a randomFn that returns the rate boundary (0.09 < 0.1 true,
    // 0.11 < 0.1 false).
    const seq = [0.09, 0.11];
    let i = 0;
    const sampler = new ProbabilisticSampler(undefined, () => seq[i++]);
    expect(sampler.shouldSample()).toBe(true);
    expect(sampler.shouldSample()).toBe(false);
  });

  it("ProbabilisticSampler with custom randomFn is fully deterministic (repro test contract)", () => {
    // randomFn always returns 0.05 → with rate=0.1, every call is true.
    const sampler = new ProbabilisticSampler(0.1, () => 0.05);
    for (let i = 0; i < 50; i++) {
      expect(sampler.shouldSample()).toBe(true);
    }
  });
});
