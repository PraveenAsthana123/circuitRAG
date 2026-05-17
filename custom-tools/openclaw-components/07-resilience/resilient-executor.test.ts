import { describe, it, expect } from "vitest";
import { CircuitBreaker } from "./circuit-breaker";
import { ResilientExecutor } from "./resilient-executor";
import { ResiliencePolicy } from "./types";
import { Timeout, TimeoutError } from "./timeout";

const policy: ResiliencePolicy = {
  timeoutMs: 100,
  maxRetries: 1,
  retryDelayMs: 10,
  failureThreshold: 2,
  resetAfterMs: 5000,
};

const context = {
  requestId: "req-1",
  sessionId: "session-1",
  userId: "user-1",
  tenantId: "tenant-1",
  traceId: "trace-1",
  component: "llm-client",
};

describe("ResilientExecutor", () => {
  it("uses (untagged) fallback when operation fails", async () => {
    const breaker = new CircuitBreaker(policy);
    const executor = new ResilientExecutor(breaker, policy);

    const result = await executor.execute(
      context,
      async (_signal) => { throw new Error("LLM provider unavailable"); },
      async () => "fallback response", // untagged → "unspecified"
    );

    expect(result.success).toBe(true);
    expect(result.fallbackUsed).toBe(true);
    expect(result.data).toBe("fallback response");
    expect(result.fallbackSource).toBe("unspecified");
  });

  it("propagates fallbackSource when caller uses tagged fallback (P1)", async () => {
    const breaker = new CircuitBreaker(policy);
    const executor = new ResilientExecutor(breaker, policy);

    const result = await executor.execute(
      context,
      async (_signal) => { throw new Error("primary failed"); },
      async () => ({ data: "from-cache", source: "cache" as const }),
    );

    expect(result.fallbackUsed).toBe(true);
    expect(result.data).toBe("from-cache");
    expect(result.fallbackSource).toBe("cache");
  });

  it("primary success path: no fallback, no fallbackSource", async () => {
    const breaker = new CircuitBreaker(policy);
    const executor = new ResilientExecutor(breaker, policy);

    const result = await executor.execute(
      context,
      async (_signal) => "primary ok",
    );

    expect(result.success).toBe(true);
    expect(result.fallbackUsed).toBe(false);
    expect(result.data).toBe("primary ok");
    expect(result.fallbackSource).toBeUndefined();
  });
});

describe("Timeout — AbortController integration (P1)", () => {
  it("signals abort to the operation on deadline", async () => {
    const timeout = new Timeout();
    let signalSeen: AbortSignal | undefined;
    let abortedFlag = false;

    const op = (signal: AbortSignal) =>
      new Promise<string>(() => {
        signalSeen = signal;
        signal.addEventListener("abort", () => { abortedFlag = true; });
        // Never resolves — only the Timeout's deadline can end this.
      });

    await expect(timeout.run(op, 30)).rejects.toBeInstanceOf(TimeoutError);
    // Drain microtasks so the abort listener has fired before assert.
    await new Promise((r) => setTimeout(r, 5));
    // BACKDOOR CHECK: pre-fix the operation got no signal at all.
    expect(signalSeen).toBeDefined();
    expect(signalSeen!.aborted).toBe(true);
    expect(abortedFlag).toBe(true);
  });

  it("does not abort when operation resolves quickly", async () => {
    const timeout = new Timeout();
    const result = await timeout.run(async (_signal) => "fast", 100);
    expect(result).toBe("fast");
  });
});
