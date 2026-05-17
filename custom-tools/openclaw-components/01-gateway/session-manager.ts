// ✅ P1 IMPROVED (2026-05-17): sessions are tenant-scoped and have
//     TTL + LRU eviction so an idle session can't pin memory
//     indefinitely. Real durability still needs Redis/Postgres per
//     CLAUDE.md §47.7 and GAPS Component 1 row "process-local Map".
//
//     What this fix does close (for single-replica deployments):
//       - Cross-tenant collision via colliding userId: sessionId is
//         now keyed by tenant + channel + user
//       - Idle memory leak: ttlMs prunes sessions whose updatedAt
//         is older than the threshold
//       - Unbounded growth: maxSessions caps total; LRU evicts
//         oldest-updated when full

import { SessionState, UserMessage } from "./types";

const DEFAULT_TTL_MS = 60 * 60 * 1000;       // 1 hour
const DEFAULT_MAX_SESSIONS = 10_000;

export class SessionManager {
  private readonly sessions = new Map<string, SessionState>();

  constructor(
    private readonly ttlMs: number = DEFAULT_TTL_MS,
    private readonly maxSessions: number = DEFAULT_MAX_SESSIONS,
  ) {
    if (ttlMs < 1) throw new Error("ttlMs must be >= 1");
    if (maxSessions < 1) throw new Error("maxSessions must be >= 1");
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

    const existing = this.sessions.get(sessionId);
    if (existing) {
      existing.history.push(message);
      existing.updatedAt = now;
      // Touch — re-insert at end so insertion-order Map approximates LRU.
      this.sessions.delete(sessionId);
      this.sessions.set(sessionId, existing);
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

    this.sessions.set(sessionId, session);
    return session;
  }

  private pruneExpired(): void {
    const cutoff = Date.now() - this.ttlMs;
    for (const [key, session] of this.sessions) {
      if (new Date(session.updatedAt).getTime() < cutoff) {
        this.sessions.delete(key);
      }
    }
  }

  private enforceCap(): void {
    while (this.sessions.size >= this.maxSessions) {
      const oldest = this.sessions.keys().next().value;
      if (oldest === undefined) break;
      this.sessions.delete(oldest);
    }
  }

  /** Test helper. */
  size(): number {
    return this.sessions.size;
  }
}
