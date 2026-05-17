import { SessionManager } from "./session-manager";
import { UserMessage, AgentResponse } from "./types";

export class Gateway {
  constructor(
    private readonly sessionManager: SessionManager
  ) {}

  async handleMessage(message: UserMessage): Promise<AgentResponse> {
    const session = this.sessionManager.getOrCreateSession(message);

    // Later this will call Agent Runtime
    return {
      sessionId: session.sessionId,
      reply: `Received: ${message.text}`,
    };
  }
}
