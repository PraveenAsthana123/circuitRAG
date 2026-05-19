// Negative drills for Iter 104 (2026-05-18): SessionPersistenceStore
// interface + injection. Locks the Phase 2.2 seam that the parallel-
// collaborator refactor introduced: SessionManager now depends on an
// injectable persistence layer, so Redis / Postgres-backed adapters
// can plug in without changing gateway code.
//
// Mirrors M3.2 storage-interface-contracts pattern: assert that the
// in-memory adapter satisfies the interface at type-check + runtime,
// drill the injection seam, and lock backcompat for the default.

import { describe, it, expect } from "vitest";
import {
  SessionManager,
  SessionPersistenceStore,
  InMemorySessionStore,
} from "./session-manager";
import { SessionState, UserMessage } from "./types";

const MSG = (
  userId: string = "u-1",
  tenantId: string = "t-1",
  text: string = "hi",
): UserMessage => ({
  messageId: `m-${Math.random().toString(36).slice(2)}`,
  userId,
  channel: "web",
  text,
  timestamp: new Date().toISOString(),
  tenantId,
});

describe("Iter 104 — SessionPersistenceStore interface contract (P1)", () => {
  it("BACKDOOR: InMemorySessionStore satisfies SessionPersistenceStore interface", () => {
    // TS compile-time check via assignment.
    const store: SessionPersistenceStore = new InMemorySessionStore();
    // Runtime check: every required method exists + is callable.
    expect(typeof store.get).toBe("function");
    expect(typeof store.set).toBe("function");
    expect(typeof store.delete).toBe("function");
    expect(typeof store.entries).toBe("function");
    expect(typeof store.oldestKey).toBe("function");
    expect(typeof store.size).toBe("function");
  });

  it("BACKDOOR: SessionManager default uses InMemorySessionStore (backcompat)", () => {
    const mgr = new SessionManager();
    expect(mgr.size()).toBe(0);
    mgr.getOrCreateSession(MSG());
    expect(mgr.size()).toBe(1);
  });

  it("BACKDOOR: injected custom store receives every read/write", () => {
    // Build a spy store that counts each call.
    class SpyStore implements SessionPersistenceStore {
      public getCalls = 0;
      public setCalls = 0;
      public deleteCalls = 0;
      private readonly map = new Map<string, SessionState>();
      get(k: string): SessionState | undefined {
        this.getCalls += 1;
        return this.map.get(k);
      }
      set(k: string, v: SessionState): void {
        this.setCalls += 1;
        this.map.set(k, v);
      }
      delete(k: string): void {
        this.deleteCalls += 1;
        this.map.delete(k);
      }
      entries(): Iterable<[string, SessionState]> { return this.map.entries(); }
      oldestKey(): string | undefined { return this.map.keys().next().value; }
      size(): number { return this.map.size; }
    }
    const spy = new SpyStore();
    const mgr = new SessionManager(60_000, 100, spy);

    mgr.getOrCreateSession(MSG());
    expect(spy.setCalls).toBeGreaterThanOrEqual(1);
    expect(spy.getCalls).toBeGreaterThanOrEqual(1);
  });

  it("BACKDOOR: touch path goes through store.delete + store.set (LRU-via-reinsert contract)", () => {
    let deleteCount = 0;
    let setCount = 0;
    const inner = new InMemorySessionStore();
    const store: SessionPersistenceStore = {
      get: (k) => inner.get(k),
      set: (k, v) => { setCount += 1; inner.set(k, v); },
      delete: (k) => { deleteCount += 1; inner.delete(k); },
      entries: () => inner.entries(),
      oldestKey: () => inner.oldestKey(),
      size: () => inner.size(),
    };
    const mgr = new SessionManager(60_000, 100, store);

    mgr.getOrCreateSession(MSG());        // create: 0 delete + 1 set
    expect(deleteCount).toBe(0);
    expect(setCount).toBe(1);

    mgr.getOrCreateSession(MSG());        // touch: 1 delete + 1 set
    expect(deleteCount).toBe(1);
    expect(setCount).toBe(2);
  });

  it("BACKDOOR: enforceCap path goes through store.oldestKey + store.delete", () => {
    let oldestKeyCalls = 0;
    let deleteCount = 0;
    const inner = new InMemorySessionStore();
    const store: SessionPersistenceStore = {
      get: (k) => inner.get(k),
      set: (k, v) => inner.set(k, v),
      delete: (k) => { deleteCount += 1; inner.delete(k); },
      entries: () => inner.entries(),
      oldestKey: () => { oldestKeyCalls += 1; return inner.oldestKey(); },
      size: () => inner.size(),
    };
    const mgr = new SessionManager(60_000, 2, store);

    mgr.getOrCreateSession(MSG("u-1"));   // size 1, below cap
    mgr.getOrCreateSession(MSG("u-2"));   // size 2, AT cap → enforceCap evicts
    mgr.getOrCreateSession(MSG("u-3"));   // size 2 again → enforceCap evicts again
    expect(oldestKeyCalls).toBeGreaterThan(0);
    expect(deleteCount).toBeGreaterThan(0);
  });

  it("BACKDOOR: pruneExpired iterates store.entries — custom store sees every key", async () => {
    let entriesCalls = 0;
    const inner = new InMemorySessionStore();
    const store: SessionPersistenceStore = {
      get: (k) => inner.get(k),
      set: (k, v) => inner.set(k, v),
      delete: (k) => inner.delete(k),
      entries: () => { entriesCalls += 1; return inner.entries(); },
      oldestKey: () => inner.oldestKey(),
      size: () => inner.size(),
    };
    const mgr = new SessionManager(50, 100, store);
    mgr.getOrCreateSession(MSG());
    await new Promise((r) => setTimeout(r, 75));  // window expires
    mgr.getOrCreateSession(MSG("u-2"));            // triggers prune
    expect(entriesCalls).toBeGreaterThan(1);
  });

  it("functional regression: cross-tenant key isolation preserved through custom store", () => {
    const inner = new InMemorySessionStore();
    const store: SessionPersistenceStore = {
      get: (k) => inner.get(k),
      set: (k, v) => inner.set(k, v),
      delete: (k) => inner.delete(k),
      entries: () => inner.entries(),
      oldestKey: () => inner.oldestKey(),
      size: () => inner.size(),
    };
    const mgr = new SessionManager(60_000, 100, store);

    const a = mgr.getOrCreateSession(MSG("u-1", "tenant-A"));
    const b = mgr.getOrCreateSession(MSG("u-1", "tenant-B"));
    expect(a.sessionId).not.toBe(b.sessionId);
    expect(a.tenantId).toBe("tenant-A");
    expect(b.tenantId).toBe("tenant-B");
  });

  it("functional regression: history accumulation preserved through custom store", () => {
    const store = new InMemorySessionStore();
    const mgr = new SessionManager(60_000, 100, store);
    const s = mgr.getOrCreateSession(MSG("u-1", "t-1", "first"));
    mgr.getOrCreateSession(MSG("u-1", "t-1", "second"));
    mgr.getOrCreateSession(MSG("u-1", "t-1", "third"));
    expect(s.history.length).toBe(3);
  });

  it("InMemorySessionStore methods work standalone (regression — not coupled to SessionManager)", () => {
    const store = new InMemorySessionStore();
    const session: SessionState = {
      sessionId: "s-1", userId: "u", tenantId: "t",
      channel: "web", history: [], createdAt: "", updatedAt: "",
    };
    expect(store.size()).toBe(0);
    expect(store.get("s-1")).toBeUndefined();

    store.set("s-1", session);
    expect(store.size()).toBe(1);
    expect(store.get("s-1")).toBe(session);

    expect(store.oldestKey()).toBe("s-1");
    const list = Array.from(store.entries());
    expect(list.length).toBe(1);
    expect(list[0][0]).toBe("s-1");

    store.delete("s-1");
    expect(store.size()).toBe(0);
    expect(store.get("s-1")).toBeUndefined();
  });

  it("constructor without explicit store still uses InMemorySessionStore (backcompat)", () => {
    // Pre-iter-104 callers: `new SessionManager()`, `new SessionManager(ttl)`,
    // `new SessionManager(ttl, max)` all still work with no store arg.
    const a = new SessionManager();
    const b = new SessionManager(5_000);
    const c = new SessionManager(5_000, 50);
    [a, b, c].forEach((m) => {
      m.getOrCreateSession(MSG());
      expect(m.size()).toBe(1);
    });
  });
});
