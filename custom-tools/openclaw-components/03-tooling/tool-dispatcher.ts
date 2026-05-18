// ✅ Iter 16 (2026-05-17): idempotency cache integrated.
//     If request.idempotencyKey is set AND the dispatcher has seen
//     (tenantId, toolName, idempotencyKey) within the cache TTL,
//     the cached result is returned with idempotentReplay: true and
//     the tool is NOT re-executed. Caller-retry-friendly per
//     CLAUDE.md §6.3.
//
//     Default cache is in-memory (10-minute TTL, 10k entries).
//     Constructor accepts a custom IdempotencyCache so tests + prod
//     can swap it out (Redis-backed implementation would conform to
//     the same get/set interface).

import { ToolRegistry } from "./tool-registry";
import { Logger } from "./logger";
import { Telemetry } from "./telemetry";
import { ResponsibleAIGuard } from "./responsible-ai-guard";
import { ExplainabilityRecorder } from "./explainability-recorder";
import { IdempotencyCache } from "./idempotency-cache";
import { ToolRequest, ToolResult, ToolErrorMeta } from "./types";

/**
 * Iter M1.1 (2026-05-18): redact host filesystem paths from a stack
 * trace before persisting (defense-in-depth — even if a tool's
 * thrown error leaks an absolute path, the dispatcher scrubs it
 * before the dispatcher result is surfaced to the workflow engine
 * or audit log). Mirrors iter 59's engine-level redactor; inlined
 * here to keep the dispatcher independent of the workflow engine.
 */
function redactStackPaths(stack: string | undefined): string | undefined {
  if (stack === undefined) return undefined;
  return stack.split("\n").map((line) => {
    if (line.includes("(node:") || /\bat\s+node:/.test(line)) return line;
    let redacted = line.replace(
      /\(((?:file:\/\/\/?)?[^()]+?)(:\d+:\d+)\)/g,
      "([redacted]$2)",
    );
    redacted = redacted.replace(
      /(\s+at\s+)((?:file:\/\/\/?)?(?:\/|[A-Za-z]:[\\/])[^\s()]+?)(:\d+:\d+)\s*$/,
      "$1[redacted]$3",
    );
    return redacted;
  }).join("\n");
}

/**
 * Iter M1.1: build a structured ToolErrorMeta from anything thrown.
 * Captures one level of `Error.cause` (a standard ES2022 chain) so
 * the workflow audit envelope can reconstruct "tool wrapped HTTP
 * error" without unbounded depth. Non-Error throws produce a
 * NonError envelope rather than crashing.
 */
function buildErrorMeta(thrown: unknown): ToolErrorMeta {
  if (thrown instanceof Error) {
    const meta: ToolErrorMeta = {
      name: thrown.name,
      message: thrown.message,
      stack: redactStackPaths(thrown.stack),
    };
    const cause = (thrown as { cause?: unknown }).cause;
    if (cause instanceof Error) {
      meta.cause = {
        name: cause.name,
        message: cause.message,
        stack: redactStackPaths(cause.stack),
      };
    }
    return meta;
  }
  return {
    name: "NonError",
    message: typeof thrown === "string" ? thrown : JSON.stringify(thrown ?? null),
  };
}

export class ToolDispatcher {
  private readonly idempotency: IdempotencyCache;

  constructor(
    private readonly registry: ToolRegistry,
    private readonly logger: Logger,
    private readonly telemetry: Telemetry,
    private readonly guard: ResponsibleAIGuard,
    private readonly explainability: ExplainabilityRecorder,
    idempotencyCache?: IdempotencyCache,
  ) {
    this.idempotency = idempotencyCache ?? new IdempotencyCache();
  }

  async dispatch(request: ToolRequest): Promise<ToolResult> {
    const span = this.telemetry.startSpan("tool.dispatch", {
      requestId: request.context.requestId,
      sessionId: request.context.sessionId,
      toolName: request.toolName,
      tenantId: request.context.tenantId,
      traceId: request.context.traceId,
      idempotent: Boolean(request.idempotencyKey),
    });

    const start = Date.now();

    this.logger.info("Tool dispatch started", {
      requestId: request.context.requestId,
      toolName: request.toolName,
      idempotencyKey: request.idempotencyKey,
    });

    // Idempotency short-circuit: cache lookup BEFORE guard/execute.
    if (request.idempotencyKey) {
      const cacheKey = this.cacheKey(request);
      const cached = this.idempotency.get(cacheKey);
      if (cached) {
        this.telemetry.recordMetric("tool_idempotent_replay_total", 1, {
          toolName: request.toolName,
        });
        try {
          return { ...cached, idempotentReplay: true };
        } finally {
          span.end();
        }
      }
    }

    try {
      this.guard.validate(request);

      const tool = this.registry.get(request.toolName);
      this.authorize(request, tool.allowedRoles);

      const output = await tool.execute(request.input, request.context);

      const result: ToolResult = {
        success: true,
        output,
        durationMs: Date.now() - start,
      };

      this.telemetry.recordMetric("tool_success_total", 1, {
        toolName: request.toolName,
      });

      this.explainability.recordDecision(
        request,
        result,
        "Tool passed policy validation and executed successfully"
      );

      if (request.idempotencyKey) {
        this.idempotency.set(this.cacheKey(request), result);
      }

      return result;
    } catch (error) {
      // Iter M1.1 (2026-05-18): preserve structured error metadata
      // (name, stack, cause chain) so workflow engine's catch block
      // (iter 57 toErrorEnvelope) can persist the full forensic
      // trail in StepErrorEnvelope. Pre-fix, only `error.message`
      // survived, so the audit log knew "something failed" but not
      // WHAT class, WHERE in the stack, or WHAT caused it.
      const result: ToolResult = {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
        errorMeta: buildErrorMeta(error),
        durationMs: Date.now() - start,
      };

      this.logger.error("Tool dispatch failed", {
        requestId: request.context.requestId,
        toolName: request.toolName,
        error: result.error,
      });

      this.telemetry.recordMetric("tool_failure_total", 1, {
        toolName: request.toolName,
      });

      this.explainability.recordDecision(
        request,
        result,
        "Tool failed due to validation, lookup, or execution error"
      );

      // Deliberate: failures are NOT cached. Retries with the same
      // idempotency key after a failure should re-run (caller may
      // have fixed input or the underlying issue resolved).
      return result;
    } finally {
      span.end();
    }
  }

  private authorize(request: ToolRequest, allowedRoles: string[]): void {
    if (allowedRoles.length === 0) return;

    const callerRoles = request.context.roles ?? [];
    const allowed = callerRoles.some((role) => allowedRoles.includes(role));

    if (!allowed) {
      throw new Error("Tool access denied: " + request.toolName);
    }
  }

  private cacheKey(request: ToolRequest): string {
    // Per-tenant scoping is mandatory — same idempotency key from
    // two tenants must hit different cache slots.
    return `${request.context.tenantId}:${request.toolName}:${request.idempotencyKey}`;
  }
}
