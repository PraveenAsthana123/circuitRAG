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
import { ToolRequest, ToolResult } from "./types";

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
      const result: ToolResult = {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
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
