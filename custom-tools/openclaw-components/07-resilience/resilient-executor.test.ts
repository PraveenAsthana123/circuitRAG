import { describe, it, expect } from "vitest";
import { CircuitBreaker } from "./circuit-breaker";
import { ResilientExecutor } from "./resilient-executor";
import { ResiliencePolicy } from "./types";

describe("ResilientExecutor", () => {
  it("uses fallback when operation fails", async () => {
    const policy: ResiliencePolicy = {
      timeoutMs: 100,
      maxRetries: 1,
      retryDelayMs: 10,
      failureThreshold: 2,
      resetAfterMs: 5000,
    };

    const breaker = new CircuitBreaker(policy);
    const executor = new ResilientExecutor(breaker, policy);

    const result = await executor.execute(
      {
        requestId: "req-1",
        sessionId: "session-1",
        userId: "user-1",
        tenantId: "tenant-1",
        traceId: "trace-1",
        component: "llm-client",
      },
      async () => {
        throw new Error("LLM provider unavailable");
      },
      async () => "fallback response"
    );

    expect(result.success).toBe(true);
    expect(result.fallbackUsed).toBe(true);
    expect(result.data).toBe("fallback response");
  });
});
