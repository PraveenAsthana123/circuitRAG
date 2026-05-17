// Added 2026-05-17 (Iter 11) — in-memory sliding-window rate limiter
// for the Gateway. Per-tenant + per-IP buckets. Real production
// should use Redis with TTL keys for horizontal scaling — see GAPS.md
// Component 1 row "No rate limit". This in-memory version closes
// the GAPS row for SINGLE-replica deployments and gives the right
// shape for the Redis swap.

const DEFAULT_LIMIT = 100;
const DEFAULT_WINDOW_MS = 60_000;

export class RateLimiter {
  private readonly buckets = new Map<string, number[]>();

  constructor(
    private readonly limit: number = DEFAULT_LIMIT,
    private readonly windowMs: number = DEFAULT_WINDOW_MS,
  ) {
    if (limit < 1) throw new Error("limit must be >= 1");
    if (windowMs < 1) throw new Error("windowMs must be >= 1");
  }

  /**
   * Returns true if the request is allowed, false if it would
   * exceed the limit. Caller is responsible for the 429 response.
   */
  tryAcquire(key: string): boolean {
    const now = Date.now();
    const cutoff = now - this.windowMs;
    const bucket = this.buckets.get(key) ?? [];

    // Prune timestamps outside the window.
    let firstFresh = 0;
    while (firstFresh < bucket.length && bucket[firstFresh] < cutoff) {
      firstFresh++;
    }
    const fresh = firstFresh > 0 ? bucket.slice(firstFresh) : bucket;

    if (fresh.length >= this.limit) {
      this.buckets.set(key, fresh);
      return false;
    }
    fresh.push(now);
    this.buckets.set(key, fresh);
    return true;
  }

  /** Test helper. */
  countInWindow(key: string): number {
    return this.buckets.get(key)?.length ?? 0;
  }
}
