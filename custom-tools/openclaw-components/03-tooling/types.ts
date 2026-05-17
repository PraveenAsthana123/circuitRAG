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
  /**
   * Optional idempotency key (CLAUDE.md §6.3). If supplied AND the
   * dispatcher has seen this (toolName, idempotencyKey) within its
   * cache TTL, the cached result is returned WITHOUT re-executing.
   * Use for write-operations the caller might retry (e.g., network
   * blip, button mash). Per-tenant scope is enforced internally.
   */
  idempotencyKey?: string;
}

export interface ToolResult {
  success: boolean;
  output?: unknown;
  error?: string;
  durationMs: number;
  /** True when this result was served from the idempotency cache. */
  idempotentReplay?: boolean;
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
