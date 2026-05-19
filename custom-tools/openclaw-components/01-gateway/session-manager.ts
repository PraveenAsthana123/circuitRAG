// ✅ P1 IMPROVED (2026-05-17): sessions are tenant-scoped and have
//     TTL + LRU eviction so an idle session can't pin memory
//     indefinitely.
// ✅ Iter 98 (2026-05-18): SessionManager now depends on an
//     injectable SessionPersistenceStore. The default remains the
//     bounded in-memory adapter for local/test, but Redis/Postgres
//     adapters can plug in without changing gateway code.

import { SessionState, UserMessage } from "./types";

const DEFAULT_TTL_MS = 60 * 60 * 1000;       // 1 hour
const DEFAULT_MAX_SESSIONS = 10_000;

export interface SessionPersistenceStore {
  get(sessionId: string): SessionState | undefined;
  set(sessionId: string, session: SessionState): void;
  delete(sessionId: string): void;
  entries(): Iterable<[string, SessionState]>;
  oldestKey(): string | undefined;
  size(): number;
}

export class InMemorySessionStore implements SessionPersistenceStore {
  private readonly sessions = new Map<string, SessionState>();

  get(sessionId: string): SessionState | undefined {
    return this.sessions.get(sessionId);
  }

  set(sessionId: string, session: SessionState): void {
    this.sessions.set(sessionId, session);
  }

  delete(sessionId: string): void {
    this.sessions.delete(sessionId);
  }

  entries(): Iterable<[string, SessionState]> {
    return this.sessions.entries();
  }

  oldestKey(): string | undefined {
    return this.sessions.keys().next().value;
  }

  size(): number {
    return this.sessions.size;
  }
}

export class SessionManager {
  private readonly store: SessionPersistenceStore;

  constructor(
    private readonly ttlMs: number = DEFAULT_TTL_MS,
    private readonly maxSessions: number = DEFAULT_MAX_SESSIONS,
    store?: SessionPersistenceStore,
  ) {
    if (ttlMs < 1) throw new Error("ttlMs must be >= 1");
    if (maxSessions < 1) throw new Error("maxSessions must be >= 1");
    this.store = store ?? new InMemorySessionStore();
  }

  private sessionKey(message: UserMessage): string {
    const tenantId = message.tenantId ?? "default";
    return `${tenantId}:${message.channel}:${message.userId}`;
  }

  getOrCreateSession(message: UserMessage): SessionState {
    this.pruneExpired();
    this.enforceCap();

    const sessionId = this.sessionKey(message);
    const now = new Date().toISOString();

    const existing = this.store.get(sessionId);
    if (existing) {
      existing.history.push(message);
      existing.updatedAt = now;
      // Touch — re-insert at end so insertion-order stores approximate LRU.
      this.store.delete(sessionId);
      this.store.set(sessionId, existing);
      return existing;
    }

    const session: SessionState = {
      sessionId,
      userId: message.userId,
      tenantId: message.tenantId ?? "default",
      channel: message.channel,
      history: [message],
      createdAt: now,
      updatedAt: now,
    };

    this.store.set(sessionId, session);
    return session;
  }

  private pruneExpired(): void {
    const cutoff = Date.now() - this.ttlMs;
    for (const [key, session] of this.store.entries()) {
      if (new Date(session.updatedAt).getTime() < cutoff) {
        this.store.delete(key);
      }
    }
  }

  private enforceCap(): void {
    while (this.store.size() >= this.maxSessions) {
      const oldest = this.store.oldestKey();
      if (oldest === undefined) break;
      this.store.delete(oldest);
    }
  }

  /** Test helper. */
  size(): number {
    return this.store.size();
  }
}
