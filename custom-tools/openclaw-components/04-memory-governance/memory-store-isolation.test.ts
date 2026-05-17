// Negative drills for Iter 15 (2026-05-17):
//   - MemoryStore tenant isolation (P0)
//   - Indexed findByKey (P2 — sanity perf, not microbenchmark)
//   - rollbackToVersion multi-version path (P2)

import { describe, it, expect } from "vitest";
import {
  MemoryStore,
  MemoryAccessDeniedError,
  MemoryNotFoundError,
} from "./memory-store";
import { MemoryRecord } from "./types";

function rec(over: Partial<MemoryRecord> = {}): MemoryRecord {
  return {
    memoryId: "m1",
    tenantId: "tenant-A",
    userId: "user-1",
    scope: "user",
    key: "prefers_lang",
    value: "TypeScript",
    version: 1,
    createdAt: "2026-05-17T00:00:00.000Z",
    updatedAt: "2026-05-17T00:00:00.000Z",
    ...over,
  };
}

describe("MemoryStore — tenant isolation (P0)", () => {
  it("get with wrong tenant throws AccessDenied (BACKDOOR CHECK)", () => {
    const store = new MemoryStore();
    store.upsert(rec({ tenantId: "tenant-A" }));
    expect(() => store.get("m1", "tenant-B"))
      .toThrowError(MemoryAccessDeniedError);
    expect(() => store.get("m1", "tenant-A"))
      .not.toThrow();
  });

  it("get unknown memoryId throws NotFound regardless of tenant", () => {
    const store = new MemoryStore();
    expect(() => store.get("does-not-exist", "tenant-A"))
      .toThrowError(MemoryNotFoundError);
  });

  it("upsert hijack attempt: changing tenantId on same memoryId rejected", () => {
    const store = new MemoryStore();
    store.upsert(rec({ tenantId: "tenant-A" }));
    expect(() =>
      store.upsert(rec({ tenantId: "tenant-B", version: 2 })),
    ).toThrowError(MemoryAccessDeniedError);
  });

  it("delete with wrong tenant throws AccessDenied", () => {
    const store = new MemoryStore();
    store.upsert(rec({ tenantId: "tenant-A" }));
    expect(() => store.delete("m1", "tenant-B"))
      .toThrowError(MemoryAccessDeniedError);
    // owner can delete fine
    store.delete("m1", "tenant-A");
    expect(() => store.get("m1", "tenant-A"))
      .toThrowError(MemoryNotFoundError);
  });
});

describe("MemoryStore — indexed findByKey (P2)", () => {
  it("findByKey returns the right record across many inserts", () => {
    const store = new MemoryStore();
    for (let i = 0; i < 100; i++) {
      store.upsert(rec({
        memoryId: `m${i}`,
        tenantId: `tenant-${i % 3}`,
        userId: `user-${i % 5}`,
        key: `key-${i}`,
      }));
    }
    const found = store.findByKey("tenant-0", "user-0", "key-15");
    // i=15: tenant-(15%3)=tenant-0, user-(15%5)=user-0, key-15 ✓
    expect(found?.memoryId).toBe("m15");
  });

  it("findByKey isolates across tenants (same key, different tenant)", () => {
    const store = new MemoryStore();
    store.upsert(rec({ memoryId: "ma", tenantId: "A", userId: "u", key: "k", value: "A-val" }));
    store.upsert(rec({ memoryId: "mb", tenantId: "B", userId: "u", key: "k", value: "B-val" }));
    expect(store.findByKey("A", "u", "k")?.value).toBe("A-val");
    expect(store.findByKey("B", "u", "k")?.value).toBe("B-val");
  });
});

describe("MemoryStore — rollbackToVersion (P2)", () => {
  it("rollbackToVersion(N) restores version N + discards everything after", () => {
    const store = new MemoryStore();
    store.upsert(rec({ value: "v1", version: 1 }));
    store.upsert(rec({ value: "v2", version: 2 }));
    store.upsert(rec({ value: "v3", version: 3 }));
    // History contains v1, v2; current is v3.
    const restored = store.rollbackToVersion("m1", 1, "tenant-A");
    expect(restored.value).toBe("v1");
    // current is now v1; history is empty (v2 was discarded too).
    expect(store.get("m1", "tenant-A").value).toBe("v1");
  });

  it("rollbackToVersion(missing) throws", () => {
    const store = new MemoryStore();
    store.upsert(rec({ value: "v1", version: 1 }));
    store.upsert(rec({ value: "v2", version: 2 }));
    expect(() => store.rollbackToVersion("m1", 99, "tenant-A"))
      .toThrow(/no historical version 99/);
  });

  it("rollbackToVersion enforces tenant", () => {
    const store = new MemoryStore();
    store.upsert(rec({ value: "v1", version: 1, tenantId: "A" }));
    store.upsert(rec({ value: "v2", version: 2, tenantId: "A" }));
    expect(() => store.rollbackToVersion("m1", 1, "B"))
      .toThrowError(MemoryAccessDeniedError);
  });
});
