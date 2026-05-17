import { ToolRequest, ToolResult } from "./types";

export class ExplainabilityRecorder {
  recordDecision(
    request: ToolRequest,
    result: ToolResult,
    reason: string
  ): void {
    console.log(JSON.stringify({
      type: "explainability",
      requestId: request.context.requestId,
      sessionId: request.context.sessionId,
      toolName: request.toolName,
      reason,
      success: result.success,
      durationMs: result.durationMs,
      timestamp: new Date().toISOString(),
    }));
  }
}
