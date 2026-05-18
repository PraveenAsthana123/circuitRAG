// Negative drills for Iter 75 (2026-05-17): IdempotencyCache
// bounds + validation drill.
//
// Pre-fix: existing 6 idempotency tests cover the dispatcher-level
// flow (cache replay, tenant scoping, no-key path, failure non-
// caching, TTL expiry). What's NOT drilled at the unit level:
//   - maxEntries cap behavior (LRU eviction when full)
//   - constructor validation (ttlMs<1, maxEntries<1, non-integer)
//   - lazy expiry on get() (removes the entry as a side effect)
//   - re-set of same key behavior (entry TTL resets — sliding window)
//   - size() helper accuracy under churn
//   - prune() called on set() (regression — prune semantics are
//     load-bearing for the LRU eviction loop)
//
// Mirrors iter 56 + iter 58 bounds-checking discipline.

import { describe, it, expect } from "vitest";
import { IdempotencyCache } from "./idempotency-cache";
import { ToolResult } from "./types";

const RESULT = (n: number): ToolResult => ({
  success: true,
  output: { n },
  durationMs: 1,
});

describe("Iter 75 — IdempotencyCache bounds (P2)", () => {
  it("BACKDOOR: maxEntries cap evicts oldest entry when full (LRU on insertion)", () => {
    const cache = new IdempotencyCache(60_000, 3);
    cache.set("k1", RESULT(1));
    cache.set("k2", RESULT(2));
    cache.set("k3", RESULT(3));
    expect(cache.size()).toBe(3);

    // Inserting a 4th entry evicts the oldest (k1) per prune()'s
    // while-loop. With size already at cap, the eviction happens
    // BEFORE the new set lands.
    cache.set("k4", RESULT(4));
    expect(cache.size()).toBe(3);
    expect(cache.get("k1")).toBeUndefined(); // evicted
    expect(cache.get("k4")).toBeDefined();   // present
  });

  it("BACKDOOR: lazy expiry on get() removes the expired entry as a side effect", async () => {
    const cache = new IdempotencyCache(50, 100);  // 50ms TTL
    cache.set("kx", RESULT(99));
    expect(cache.size()).toBe(1);

    await new Promise((resolve) => setTimeout(resolve, 75));

    // get() of expired key returns undefined AND removes the entry.
    expect(cache.get("kx")).toBeUndefined();
    expect(cache.size()).toBe(0);
  });

  it("prune() called on set() removes expired entries", async () => {
    // Set 3 entries with a very short TTL.
    const cache = new IdempotencyCache(50, 100);
    cache.set("ka", RESULT(1));
    cache.set("kb", RESULT(2));
    cache.set("kc", RESULT(3));
    expect(cache.size()).toBe(3);

    await new Promise((resolve) => setTimeout(resolve, 75));

    // Setting a NEW key triggers prune() which sweeps the 3 expired
    // entries; only the new one remains.
    cache.set("kd", RESULT(4));
    expect(cache.size()).toBe(1);
    expect(cache.get("kd")).toBeDefined();
  });

  it("constructor rejects sub-1 ttlMs", () => {
    expect(() => new IdempotencyCache(0)).toThrow(/ttlMs/);
    expect(() => new IdempotencyCache(-100)).toThrow(/ttlMs/);
  });

  it("constructor rejects sub-1 maxEntries", () => {
    expect(() => new IdempotencyCache(60_000, 0)).toThrow(/maxEntries/);
    expect(() => new IdempotencyCache(60_000, -5)).toThrow(/maxEntries/);
  });

  it("re-set of same key UPDATES the entry (sliding-window TTL semantics)", async () => {
    const cache = new IdempotencyCache(100, 100);  // 100ms TTL
    cache.set("k", RESULT(1));

    // Wait nearly through the TTL window.
    await new Promise((resolve) => setTimeout(resolve, 70));

    // Re-set the same key with a new result. This should reset the
    // expiry window — the entry should survive past the ORIGINAL
    // expiry time.
    cache.set("k", RESULT(2));

    // Wait past the original expiry but well within the renewed one.
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Should still be present (renewed) with the NEW value.
    const got = cache.get("k");
    expect(got).toBeDefined();
    expect((got!.output as { n: number }).n).toBe(2);
  });

  it("size() accurately reflects entry count under churn", () => {
    const cache = new IdempotencyCache(60_000, 100);
    expect(cache.size()).toBe(0);
    cache.set("a", RESULT(1));
    cache.set("b", RESULT(2));
    cache.set("c", RESULT(3));
    expect(cache.size()).toBe(3);
    cache.get("a");  // not expired — size unchanged
    expect(cache.size()).toBe(3);
  });

  it("get() of never-set key returns undefined (no crash)", () => {
    const cache = new IdempotencyCache();
    expect(cache.get("never-set")).toBeUndefined();
  });

  it("works with maxEntries=1 (edge): each set evicts the previous", () => {
    const cache = new IdempotencyCache(60_000, 1);
    cache.set("first", RESULT(1));
    expect(cache.get("first")).toBeDefined();

    cache.set("second", RESULT(2));
    expect(cache.size()).toBe(1);
    expect(cache.get("first")).toBeUndefined();  // evicted
    expect(cache.get("second")).toBeDefined();
  });
});
