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

/**
 * Iter M1.1 (2026-05-18): structured error metadata for failed
 * dispatch. Pre-fix the dispatcher only carried `error: string`,
 * so the workflow engine's catch block (iter 57 toErrorEnvelope)
 * had no way to preserve the original error class, stack, or
 * cause chain — every dispatch failure became a generic Error
 * with no forensic trail. The new fields are OPTIONAL so existing
 * test fixtures remain valid; the dispatcher populates them on
 * the failure path.
 *
 * Stack + message are redacted per iter 59/60 policies before
 * being persisted, so host paths and PII don't leak through the
 * audit envelope.
 */
export interface ToolErrorMeta {
  /** Error class name (e.g., "TimeoutError", "TypeError"). */
  name: string;
  /** Human-readable message, sanitized per iter 60 PII rules. */
  message: string;
  /** Stack trace, redacted per iter 59 path-redaction rules.
   *  Optional — some platforms / pre-fix throws may lack a stack. */
  stack?: string;
  /** Underlying `Error.cause` chain when one is present. Captures
   *  one level of nesting — enough for "tool wrapped an HTTP error"
   *  forensic reconstruction without unbounded depth. */
  cause?: {
    name: string;
    message: string;
    stack?: string;
  };
}

export interface ToolResult {
  success: boolean;
  output?: unknown;
  error?: string;
  durationMs: number;
  /** True when this result was served from the idempotency cache. */
  idempotentReplay?: boolean;
  /** Iter M1.1: structured error metadata when success === false.
   *  Carries the original error class + stack + cause chain so the
   *  workflow engine can persist them in StepErrorEnvelope.cause
   *  rather than losing them in a bare `new Error(result.error)`. */
  errorMeta?: ToolErrorMeta;
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
