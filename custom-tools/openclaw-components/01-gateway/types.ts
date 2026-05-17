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
}

export interface AgentResponse {
  sessionId: string;
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
  channel: ChannelType;
  history: UserMessage[];
  createdAt: string;
  updatedAt: string;
}
