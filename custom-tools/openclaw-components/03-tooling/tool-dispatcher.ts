import { ToolRegistry } from "./tool-registry";
import { Logger } from "./logger";
import { Telemetry } from "./telemetry";
import { ResponsibleAIGuard } from "./responsible-ai-guard";
import { ExplainabilityRecorder } from "./explainability-recorder";
import { ToolRequest, ToolResult } from "./types";

export class ToolDispatcher {
  constructor(
    private readonly registry: ToolRegistry,
    private readonly logger: Logger,
    private readonly telemetry: Telemetry,
    private readonly guard: ResponsibleAIGuard,
    private readonly explainability: ExplainabilityRecorder
  ) {}

  async dispatch(request: ToolRequest): Promise<ToolResult> {
    const span = this.telemetry.startSpan("tool.dispatch", {
      requestId: request.context.requestId,
      sessionId: request.context.sessionId,
      toolName: request.toolName,
      tenantId: request.context.tenantId,
    });

    const start = Date.now();

    this.logger.info("Tool dispatch started", {
      requestId: request.context.requestId,
      toolName: request.toolName,
    });

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
}
