import { describe, expect, it } from "vitest";
import {
  InMemorySessionStore,
  SessionManager,
  SessionPersistenceStore,
} from "./session-manager";
import { SessionState, UserMessage } from "./types";

class SpySessionStore implements SessionPersistenceStore {
  readonly calls: string[] = [];
  private readonly inner = new InMemorySessionStore();

  get(sessionId: string): SessionState | undefined {
    this.calls.push(`get:${sessionId}`);
    return this.inner.get(sessionId);
  }
  set(sessionId: string, session: SessionState): void {
    this.calls.push(`set:${sessionId}`);
    this.inner.set(sessionId, session);
  }
  delete(sessionId: string): void {
    this.calls.push(`delete:${sessionId}`);
    this.inner.delete(sessionId);
  }
  entries(): Iterable<[string, SessionState]> {
    this.calls.push("entries");
    return this.inner.entries();
  }
  oldestKey(): string | undefined {
    this.calls.push("oldestKey");
    return this.inner.oldestKey();
  }
  size(): number {
    this.calls.push("size");
    return this.inner.size();
  }
}

let counter = 0;
function msg(userId: string, tenantId = "tenant-1", text = "hi"): UserMessage {
  counter += 1;
  return {
    messageId: `m-${counter}`,
    userId,
    channel: "web",
    text,
    timestamp: new Date().toISOString(),
    tenantId,
  };
}

describe("SessionManager store injection", () => {
  it("BACKDOOR: uses injected store for create and touch paths", () => {
    const store = new SpySessionStore();
    const manager = new SessionManager(60_000, 100, store);

    const first = manager.getOrCreateSession(msg("u", "t", "first"));
    const second = manager.getOrCreateSession(msg("u", "t", "second"));

    expect(first.sessionId).toBe(second.sessionId);
    expect(second.history.map((m) => m.text)).toEqual(["first", "second"]);
    expect(store.calls.some((call) => call.startsWith("set:t:web:u"))).toBe(true);
    expect(store.calls.some((call) => call.startsWith("delete:t:web:u"))).toBe(true);
  });

  it("default in-memory store preserves existing public behavior", () => {
    const manager = new SessionManager(60_000, 100);

    manager.getOrCreateSession(msg("u-a"));
    manager.getOrCreateSession(msg("u-b"));

    expect(manager.size()).toBe(2);
  });

  it("in-memory store exposes a bounded adapter contract for future Redis/Postgres stores", () => {
    const store = new InMemorySessionStore();
    const session = new SessionManager(60_000, 100, store).getOrCreateSession(msg("u"));

    expect(store.get(session.sessionId)?.sessionId).toBe(session.sessionId);
    expect([...store.entries()]).toHaveLength(1);
    expect(store.oldestKey()).toBe(session.sessionId);
    store.delete(session.sessionId);
    expect(store.size()).toBe(0);
  });
});
