import { randomUUID } from "crypto";
import { AIOpsEvent, ObservabilityContext } from "./types";
import { StructuredLogger } from "./logger";
import { MetricsRecorder } from "./metrics";
import { Tracer } from "./tracer";
import { AIOpsEventBus } from "./aiops-event-bus";

export class ObservabilityService {
  constructor(
    private readonly logger: StructuredLogger,
    private readonly metrics: MetricsRecorder,
    private readonly tracer: Tracer,
    private readonly aiops: AIOpsEventBus
  ) {}

  traceOperation<T>(
    spanName: string,
    context: ObservabilityContext,
    operation: () => Promise<T>
  ): Promise<T> {
    const span = this.tracer.startSpan(spanName, { ...context });

    const start = Date.now();

    this.logger.log("info", "Operation started", {
      spanName,
      ...context,
    });

    return operation()
      .then((result) => {
        const durationMs = Date.now() - start;

        this.metrics.histogram("operation_duration_ms", durationMs, {
          component: context.component,
          tenantId: context.tenantId,
        });

        this.metrics.counter("operation_success_total", 1, {
          component: context.component,
        });

        span.end("ok");

        return result;
      })
      .catch((error) => {
        const durationMs = Date.now() - start;

        this.metrics.counter("operation_failure_total", 1, {
          component: context.component,
        });

        this.logger.log("error", "Operation failed", {
          error: error instanceof Error ? error.message : "Unknown error",
          durationMs,
          ...context,
        });

        this.publishAIOpsEvent({
          severity: "error",
          category: "runtime",
          message: "Operation failed",
          context,
        });

        span.end("error", {
          error: error instanceof Error ? error.message : "Unknown error",
        });

        throw error;
      });
  }

  publishAIOpsEvent(input: Omit<AIOpsEvent, "eventId" | "timestamp">): void {
    this.aiops.publish({
      eventId: randomUUID(),
      timestamp: new Date().toISOString(),
      ...input,
    });
  }
}
