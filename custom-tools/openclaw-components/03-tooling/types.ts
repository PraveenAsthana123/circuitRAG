export type RiskLevel = "low" | "medium" | "high" | "blocked";

export interface ToolContext {
  requestId: string;
  sessionId: string;
  userId: string;
  tenantId: string;
  traceId?: string;
  roles?: string[];
}

export interface ToolRequest {
  toolName: string;
  input: Record<string, unknown>;
  context: ToolContext;
}

export interface ToolResult {
  success: boolean;
  output?: unknown;
  error?: string;
  durationMs: number;
}

export interface ToolDefinition {
  name: string;
  description: string;
  riskLevel: RiskLevel;
  allowedRoles: string[];

  execute(
    input: Record<string, unknown>,
    context: ToolContext
  ): Promise<unknown>;
}
