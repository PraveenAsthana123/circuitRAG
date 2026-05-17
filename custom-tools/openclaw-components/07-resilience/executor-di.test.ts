// Negative drills for Iter 32 (2026-05-17): ResilientExecutor DI.
// Pre-fix: Timeout / RetryPolicy / FallbackHandler were `new`'d at
// field-init, making the class untestable in isolation. Now they
// can be injected.

import { describe, it, expect, vi } from "vitest";
import { CircuitBreaker } from "./circuit-breaker";
import { ResilientExecutor } from "./resilient-executor";
import { ResiliencePolicy } from "./types";
import { RetryPolicy } from "./retry-policy";
import { Timeout } from "./timeout";
import { FallbackHandler } from "./fallback-handler";

const POLICY: ResiliencePolicy = {
  timeoutMs: 100,
  maxRetries: 2,
  retryDelayMs: 1,
  failureThreshold: 5,
  resetAfterMs: 5_000,
};

const CTX = {
  requestId: "r", sessionId: "s", userId: "u",
  tenantId: "t", traceId: "tr", component: "x",
};

describe("ResilientExecutor — DI (P2)", () => {
  it("BACKDOOR CHECK: injected RetryPolicy is the one actually used", async () => {
    const breaker = new CircuitBreaker(POLICY);
    // Custom retry that COUNTS calls. Pre-fix you couldn't observe
    // this because RetryPolicy was instantiated internally.
    const calls = { execute: 0 };
    class CountingRetry extends RetryPolicy {
      async execute<T>(op: () => Promise<T>, max: number, delay: number) {
        calls.execute++;
        return super.execute(op, max, delay);
      }
    }
    const exec = new ResilientExecutor(breaker, POLICY, {
      retry: new CountingRetry(),
    });

    await exec.execute(CTX, async () => "ok");
    expect(calls.execute).toBe(1);
  });

  it("injected FallbackHandler can be a spy", async () => {
    const breaker = new CircuitBreaker(POLICY);
    const handler = new FallbackHandler();
    const spy = vi.spyOn(handler, "executeFallback");
    const exec = new ResilientExecutor(breaker, POLICY, {
      fallbackHandler: handler,
    });
    await exec.execute(
      CTX,
      async () => { throw new Error("boom"); },
      async () => ({ data: "fb", source: "cache" as const }),
    );
    expect(spy).toHaveBeenCalled();
  });

  it("injected Timeout receives the call", async () => {
    const breaker = new CircuitBreaker(POLICY);
    const timeout = new Timeout();
    const spy = vi.spyOn(timeout, "run");
    const exec = new ResilientExecutor(breaker, POLICY, {
      timeout,
    });
    await exec.execute(CTX, async () => "ok");
    expect(spy).toHaveBeenCalled();
  });

  it("backcompat: omitting deps uses defaults (still works)", async () => {
    const breaker = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(breaker, POLICY);
    const result = await exec.execute(CTX, async () => "ok");
    expect(result.success).toBe(true);
    expect(result.data).toBe("ok");
  });
});
