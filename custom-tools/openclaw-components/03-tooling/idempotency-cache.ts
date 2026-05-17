// Added 2026-05-17 (Iter 16) — in-memory idempotency cache for the
// ToolDispatcher. Real production needs Redis with TTL keys for
// horizontal correctness; in-memory only protects single-replica.
// See GAPS Component 3 row.

import { ToolResult } from "./types";

const DEFAULT_TTL_MS = 10 * 60 * 1000; // 10 minutes
const DEFAULT_MAX_ENTRIES = 10_000;

interface CacheEntry {
  result: ToolResult;
  expiresAt: number;
}

export class IdempotencyCache {
  private readonly entries = new Map<string, CacheEntry>();

  constructor(
    private readonly ttlMs: number = DEFAULT_TTL_MS,
    private readonly maxEntries: number = DEFAULT_MAX_ENTRIES,
  ) {
    if (ttlMs < 1) throw new Error("ttlMs must be >= 1");
    if (maxEntries < 1) throw new Error("maxEntries must be >= 1");
  }

  /**
   * key MUST include (tenantId, toolName, idempotencyKey). Construction
   * is the caller's responsibility — keeps the cache agnostic.
   */
  get(key: string): ToolResult | undefined {
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {
      this.entries.delete(key);
      return undefined;
    }
    return entry.result;
  }

  set(key: string, result: ToolResult): void {
    this.prune();
    this.entries.set(key, {
      result,
      expiresAt: Date.now() + this.ttlMs,
    });
  }

  private prune(): void {
    const now = Date.now();
    for (const [k, v] of this.entries) {
      if (now > v.expiresAt) this.entries.delete(k);
    }
    while (this.entries.size >= this.maxEntries) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
  }

  /** Test helper. */
  size(): number {
    return this.entries.size;
  }
}
