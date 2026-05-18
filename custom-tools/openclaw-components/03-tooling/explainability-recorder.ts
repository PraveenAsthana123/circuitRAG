import { ToolRequest, ToolResult } from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export class ExplainabilityRecorder {
  private readonly sink: EventSink;
  // Iter M3.3 (2026-05-18): pluggable sink. Reuses the EventSink
  // interface from M2.3 since explainability emissions are opaque
  // event-shaped JSON (canonical-fields contract owned by the
  // recorder, not the sink — same pattern as AIOpsEventBus).
  // Default ConsoleEventSink preserves backcompat; a future
  // DecisionAuditStoreSink (Postgres append-only per §38) plugs
  // in unchanged.
  constructor(sink?: EventSink) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  recordDecision(
    request: ToolRequest,
    result: ToolResult,
    reason: string
  ): void {
    this.sink.emit({
      type: "explainability",
      requestId: request.context.requestId,
      sessionId: request.context.sessionId,
      toolName: request.toolName,
      reason,
      success: result.success,
      durationMs: result.durationMs,
      timestamp: new Date().toISOString(),
    });
  }
}
