import { describe, it, expect } from "vitest";
import { ObservabilityService } from "./observability-service";
import { StructuredLogger } from "./logger";
import { MetricsRecorder } from "./metrics";
import { Tracer } from "./tracer";
import { AIOpsEventBus } from "./aiops-event-bus";

describe("ObservabilityService", () => {
  it("traces a successful operation", async () => {
    const service = new ObservabilityService(
      new StructuredLogger(),
      new MetricsRecorder(),
      new Tracer(),
      new AIOpsEventBus()
    );

    const result = await service.traceOperation(
      "agent.plan",
      {
        requestId: "req-1",
        sessionId: "session-1",
        userId: "user-1",
        tenantId: "tenant-1",
        traceId: "trace-1",
        component: "planner",
      },
      async () => "ok"
    );

    expect(result).toBe("ok");
  });
});
