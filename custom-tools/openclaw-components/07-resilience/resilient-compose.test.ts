// Negative drills for Iter 90 (2026-05-18): ResilientExecutor
// COMPOSITIONAL drill — exercises the CB + Retry + Timeout +
// Fallback combination end-to-end. Existing tests check each
// dep is wired via DI; this tests the orchestration.

import { describe, it, expect } from "vitest";
import { ResilientExecutor } from "./resilient-executor";
import { CircuitBreaker } from "./circuit-breaker";
import { ResiliencePolicy, ResilienceContext } from "./types";

const POLICY: ResiliencePolicy = {
  timeoutMs: 100,
  maxRetries: 2,
  retryDelayMs: 1,
  failureThreshold: 3,
  resetAfterMs: 50,
};

const CTX: ResilienceContext = {
  requestId: "r-1", component: "test", traceId: "tr",
};

describe("Iter 90 — ResilientExecutor composition (P1)", () => {
  it("BACKDOOR: success path returns data + fallbackUsed=false + records CB success", async () => {
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY);
    const result = await exec.execute(CTX, async () => "ok");
    expect(result.success).toBe(true);
    expect(result.data).toBe("ok");
    expect(result.fallbackUsed).toBe(false);
    expect(cb.getState()).toBe("closed");
  });

  it("BACKDOOR: retry retries the configured number of times before failure", async () => {
    let calls = 0;
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY);
    const result = await exec.execute(CTX, async () => {
      calls += 1;
      throw new Error("transient");
    });
    // policy.maxRetries=2 means 1 initial + 2 retries = 3 calls total.
    expect(calls).toBe(1 + POLICY.maxRetries);
    // Failure → no fallback registered → success: false.
    expect(result.success).toBe(false);
  });

  it("BACKDOOR: fallback is used when primary fails AND fallback provided", async () => {
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY);
    const result = await exec.execute<string>(
      CTX,
      async () => { throw new Error("nope"); },
      async () => "fallback-value",
    );
    expect(result.success).toBe(true);
    expect(result.data).toBe("fallback-value");
    expect(result.fallbackUsed).toBe(true);
  });

  it("BACKDOOR: CB open → primary NOT called, fallback runs immediately", async () => {
    const cb = new CircuitBreaker(POLICY);
    // Force open by tripping the threshold.
    for (let i = 0; i < POLICY.failureThreshold; i++) cb.recordFailure();
    expect(cb.getState()).toBe("open");

    let primaryCalled = false;
    const exec = new ResilientExecutor(cb, POLICY);
    const result = await exec.execute<string>(
      CTX,
      async () => { primaryCalled = true; return "should not happen"; },
      async () => "shortcut-fallback",
    );
    expect(primaryCalled).toBe(false);
    expect(result.fallbackUsed).toBe(true);
    expect(result.data).toBe("shortcut-fallback");
  });

  it("BACKDOOR: timeout propagates to primary then triggers fallback", async () => {
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, {
      ...POLICY, timeoutMs: 50, maxRetries: 0,
    });
    const result = await exec.execute<string>(
      CTX,
      (signal) => new Promise((resolve) => {
        const id = setTimeout(() => resolve("late"), 200);
        signal.addEventListener("abort", () => clearTimeout(id));
      }),
      async () => "fast-fallback",
    );
    expect(result.fallbackUsed).toBe(true);
    expect(result.data).toBe("fast-fallback");
  });

  it("durationMs is non-negative on every outcome", async () => {
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY);
    const ok = await exec.execute(CTX, async () => "x");
    const fail = await exec.execute<string>(CTX, async () => {
      throw new Error("e");
    });
    expect(ok.durationMs).toBeGreaterThanOrEqual(0);
    expect(fail.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("BACKDOOR: failure WITHOUT fallback → success:false + error preserved", async () => {
    const cb = new CircuitBreaker(POLICY);
    const exec = new ResilientExecutor(cb, POLICY);
    const result = await exec.execute<string>(
      CTX,
      async () => { throw new Error("specific-msg"); },
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("specific-msg");
    expect(result.fallbackUsed).toBe(false);
  });

  it("CB records failure when primary fails (state transitions correctly)", async () => {
    const cb = new CircuitBreaker({
      ...POLICY, failureThreshold: 2, maxRetries: 0,
    });
    const exec = new ResilientExecutor(cb, {
      ...POLICY, failureThreshold: 2, maxRetries: 0,
    });
    expect(cb.getState()).toBe("closed");
    await exec.execute<string>(CTX, async () => { throw new Error("e"); });
    expect(cb.getState()).toBe("closed");  // 1 failure, below threshold
    await exec.execute<string>(CTX, async () => { throw new Error("e"); });
    expect(cb.getState()).toBe("open");    // 2 failures, threshold hit
  });

  it("CB recordSuccess on win clears the failure count toward open", async () => {
    const cb = new CircuitBreaker({
      ...POLICY, failureThreshold: 2, maxRetries: 0,
    });
    const exec = new ResilientExecutor(cb, {
      ...POLICY, failureThreshold: 2, maxRetries: 0,
    });
    await exec.execute<string>(CTX, async () => { throw new Error("e"); });
    await exec.execute(CTX, async () => "ok");  // resets
    // Another failure should NOT push to open (count was reset).
    await exec.execute<string>(CTX, async () => { throw new Error("e"); });
    expect(cb.getState()).toBe("closed");
  });
});
