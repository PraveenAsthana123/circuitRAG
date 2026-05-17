import { SessionState, UserMessage } from "./types";

export class SessionManager {
  private sessions = new Map<string, SessionState>();

  getOrCreateSession(message: UserMessage): SessionState {
    const sessionId = `${message.channel}:${message.userId}`;

    const existing = this.sessions.get(sessionId);
    if (existing) {
      existing.history.push(message);
      existing.updatedAt = new Date().toISOString();
      return existing;
    }

    const session: SessionState = {
      sessionId,
      userId: message.userId,
      channel: message.channel,
      history: [message],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    this.sessions.set(sessionId, session);
    return session;
  }
}
