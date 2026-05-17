export type ChannelType =
  | "whatsapp"
  | "telegram"
  | "slack"
  | "discord"
  | "web"
  | "cli";

export interface UserMessage {
  messageId: string;
  userId: string;
  channel: ChannelType;
  text: string;
  timestamp: string;
  // Optional tenantId — required for multi-tenant deployments
  // per CLAUDE.md §41.3. Channels that don't carry tenancy can
  // omit it; the gateway treats omitted == "default".
  tenantId?: string;
}

export interface AgentResponse {
  sessionId: string;
  // requestId minted by the gateway and propagated to every downstream
  // call (per CLAUDE.md §47 baggage propagation rule).
  requestId: string;
  reply: string;
  toolCalls?: ToolCall[];
}

export interface ToolCall {
  toolName: string;
  input: Record<string, unknown>;
}

export interface SessionState {
  sessionId: string;
  userId: string;
  tenantId: string;
  channel: ChannelType;
  history: UserMessage[];
  createdAt: string;
  updatedAt: string;
}

/**
 * Structured error envelope (CLAUDE.md §6.2).
 * Every error response from the gateway carries this shape so callers
 * can correlate via request_id and react programmatically via code.
 */
export interface ErrorEnvelope {
  detail: string;
  errorCode: string;
  requestId: string;
}

export class GatewayError extends Error {
  constructor(
    message: string,
    public readonly errorCode: string,
    public readonly statusHint: number = 500,
  ) {
    super(message);
    this.name = "GatewayError";
  }
}
