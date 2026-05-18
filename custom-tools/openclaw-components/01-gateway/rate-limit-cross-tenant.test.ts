// Iter 70 (2026-05-17) — cross-tenant isolation drill for RateLimiter.
//
// Pre-fix: Gateway already namespaces the rate-limit key by tenant
// (`${tenantId}:${userId}`), but no drill PROVES the cross-tenant
// isolation property — that tenant A burning the budget does NOT
// throttle tenant B. Without a locking drill, a future refactor that
// flattens keys (e.g. "global" bucket) silently regresses this and
// no test fails. STRIDE 'D' (denial of service) — one tenant must
// not exhaust another tenant's quota.
//
// Composes with: CLAUDE.md §43 (drill pattern, ≥1 negative assertion),
//                CLAUDE.md §47.6 (STRIDE D — DoS isolation),
//                CLAUDE.md §52 row 5 (multi-tenant isolation evidence).
//
// Drill steps (5 total; 4 negative + 1 positive):
//   1. NEGATIVE: tenant A exhausting their per-user rate limit does NOT
//      affect tenant B's identical-userId budget (the critical isolation
//      property — proves keys are partitioned, not pooled).
//   2. NEGATIVE: same tenantId + different userId have independent
//      budgets (proves the userId axis of the composite key is honored).
//   3. NEGATIVE: same tenantId + same userId — second exhaustion event
//      observed (proves the bucket isn't accidentally global / shared
//      across calls with same key).
//   4. POSITIVE: after the window expires, the budget resets for the
//      exhausted key (proves the sliding-window prune actually runs).
//   5. NEGATIVE: RateLimiter constructor rejects invalid config —
//      zero capacity AND negative window — both must throw.

import { describe, it, expect } from "vitest";
import { RateLimiter } from "./rate-limiter";

// Gateway composes the rate-limit key the same way; mirror it here
// so the drill exercises the same key shape callers will use.
const rlKey = (tenantId: string, userId: string) => `${tenantId}:${userId}`;

describe("RateLimiter — cross-tenant isolation (Iter 70, P1)", () => {
  it("BACKDOOR CHECK: tenant A exhausting per-user budget does NOT affect tenant B's same-userId budget", () => {
    // limit=2 so we can burn it fast and observe the next call's verdict.
    const rl = new RateLimiter(2, 60_000);
    const aliceInA = rlKey("tenant-A", "alice");
    const aliceInB = rlKey("tenant-B", "alice");

    // Burn tenant A's alice budget completely.
    expect(rl.tryAcquire(aliceInA)).toBe(true);
    expect(rl.tryAcquire(aliceInA)).toBe(true);
    expect(rl.tryAcquire(aliceInA)).toBe(false); // exhausted

    // The critical isolation assertion: tenant B's alice MUST still
    // acquire — same userId, different tenant, independent budget.
    // If this fails, a malicious tenant can starve every other tenant.
    expect(rl.tryAcquire(aliceInB)).toBe(true);
    expect(rl.tryAcquire(aliceInB)).toBe(true);
    expect(rl.tryAcquire(aliceInB)).toBe(false);

    // And tenant A's alice is still exhausted (proves the previous
    // tenant-B traffic didn't somehow refill tenant A's bucket).
    expect(rl.tryAcquire(aliceInA)).toBe(false);
  });

  it("BACKDOOR CHECK: same tenantId + different userId have independent budgets", () => {
    const rl = new RateLimiter(1, 60_000);
    const aliceInA = rlKey("tenant-A", "alice");
    const bobInA = rlKey("tenant-A", "bob");

    // Alice burns her single-request budget in tenant A.
    expect(rl.tryAcquire(aliceInA)).toBe(true);
    expect(rl.tryAcquire(aliceInA)).toBe(false); // exhausted

    // Bob in the SAME tenant must still acquire — the per-user axis
    // of the composite key must be honored, not collapsed to per-tenant.
    expect(rl.tryAcquire(bobInA)).toBe(true);
    expect(rl.tryAcquire(bobInA)).toBe(false);

    // Alice is still exhausted; Bob's traffic didn't refill her.
    expect(rl.tryAcquire(aliceInA)).toBe(false);
  });

  it("BACKDOOR CHECK: same tenantId + same userId — second exhaustion event observed", () => {
    // This locks the "bucket isn't accidentally shared" inverse: the
    // SAME key MUST share state. If a regression made every call use
    // a fresh bucket (e.g. forgot to .set() it back), this would
    // silently allow infinite traffic per key.
    const rl = new RateLimiter(2, 60_000);
    const key = rlKey("tenant-A", "alice");

    // First exhaustion.
    expect(rl.tryAcquire(key)).toBe(true);
    expect(rl.tryAcquire(key)).toBe(true);
    expect(rl.tryAcquire(key)).toBe(false);
    // Same key — must STILL be denied (state persists).
    expect(rl.tryAcquire(key)).toBe(false);
    expect(rl.tryAcquire(key)).toBe(false);

    // countInWindow exposes the bucket size for this key; must be
    // exactly the limit (2), not 4 (which would mean denied calls
    // were nevertheless recorded) and not 0 (which would mean state
    // didn't persist).
    expect(rl.countInWindow(key)).toBe(2);
  });

  it("after window expires, the exhausted key's budget resets", async () => {
    // Tiny window so the test runs fast.
    const rl = new RateLimiter(1, 30);
    const key = rlKey("tenant-A", "alice");

    expect(rl.tryAcquire(key)).toBe(true);
    expect(rl.tryAcquire(key)).toBe(false);

    // Wait past the window so the sliding-window prune drops the
    // earlier timestamp.
    await new Promise((r) => setTimeout(r, 50));

    expect(rl.tryAcquire(key)).toBe(true);
    // And the post-reset bucket has only the new timestamp, not 2.
    expect(rl.countInWindow(key)).toBe(1);
  });

  it("BACKDOOR CHECK: RateLimiter constructor rejects invalid config (zero capacity, negative window)", () => {
    // Zero capacity makes the limiter unconditionally deny every
    // request — a silent DoS if not blocked at construction.
    expect(() => new RateLimiter(0, 60_000)).toThrow(/limit must be/);
    // Negative capacity — likewise nonsensical.
    expect(() => new RateLimiter(-1, 60_000)).toThrow(/limit must be/);
    // Negative or zero window — sliding-window math breaks (cutoff
    // in the future means every timestamp is pruned).
    expect(() => new RateLimiter(10, 0)).toThrow(/windowMs must be/);
    expect(() => new RateLimiter(10, -100)).toThrow(/windowMs must be/);
  });
});
