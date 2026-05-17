// Negative drills for the Iteration 6 fixes (2026-05-17):
//   - CircuitBreaker half-open race condition (P0)
//   - RetryPolicy backoff jitter (P1)

import { describe, it, expect } from "vitest";
import { CircuitBreaker } from "./circuit-breaker";
import { RetryPolicy } from "./retry-policy";
import { ResiliencePolicy } from "./types";

const POLICY: ResiliencePolicy = {
  timeoutMs: 100,
  maxRetries: 3,
  retryDelayMs: 10,
  failureThreshold: 2,
  // 50ms is short enough for tests to wait 52ms in setTimeout but
  // long enough that the next-microtask canExecute() after a fresh
  // recordFailure reliably sees elapsed < resetAfterMs.
  // (Pre-fix used 1ms which was racy — synchronous canExecute()
  // after recordFailure can be either side of 1ms depending on CPU.)
  resetAfterMs: 50,
};

describe("CircuitBreaker — half-open race (P0)", () => {
  it("admits exactly ONE probe when transitioning from open to half_open", async () => {
    const cb = new CircuitBreaker(POLICY);
    cb.recordFailure();
    cb.recordFailure();
    expect(cb.getState()).toBe("open");

    // Let the reset window expire so the next canExecute promotes
    // open → half_open and admits the probe.
    await new Promise((r) => setTimeout(r, POLICY.resetAfterMs + 2));

    const probe1 = cb.canExecute();
    const probe2 = cb.canExecute();
    const probe3 = cb.canExecute();

    // BACKDOOR CHECK (pre-fix would admit all three).
    expect(probe1).toBe(true);
    expect(probe2).toBe(false);
    expect(probe3).toBe(false);
    expect(cb.getState()).toBe("half_open");
  });

  it("recordSuccess from probe closes the breaker", async () => {
    const cb = new CircuitBreaker(POLICY);
    cb.recordFailure(); cb.recordFailure();
    await new Promise((r) => setTimeout(r, POLICY.resetAfterMs + 2));
    cb.canExecute(); // probe admitted
    cb.recordSuccess();
    expect(cb.getState()).toBe("closed");
    // After close, normal traffic flows again.
    expect(cb.canExecute()).toBe(true);
  });

  it("recordFailure from probe re-opens the breaker", async () => {
    const cb = new CircuitBreaker(POLICY);
    cb.recordFailure(); cb.recordFailure();
    await new Promise((r) => setTimeout(r, POLICY.resetAfterMs + 2));
    cb.canExecute();
    cb.recordFailure();
    expect(cb.getState()).toBe("open");
    expect(cb.canExecute()).toBe(false);
  });
});

describe("RetryPolicy — jitter (P1)", () => {
  it("backoff includes jitter spread, not deterministic 2^attempt", () => {
    // Pin randomFn so the math is verifiable.
    const policyAtZero = new RetryPolicy(() => 0);
    const policyAtOne = new RetryPolicy(() => 0.999);
    const base = 100;
    const attempt = 2; // base*4 = 400

    // Min spread (random ≈ 0): base * 4 * 0.5 = 200
    expect(policyAtZero.backoffWithJitter(base, attempt)).toBe(200);
    // Max spread (random ≈ 1): base * 4 * (0.5 + 0.999) ≈ 599
    expect(policyAtOne.backoffWithJitter(base, attempt)).toBe(599);

    // BACKDOOR CHECK: a deterministic `base * 2^attempt` would return
    // 400 in both cases. Jittered version must NOT.
    expect(policyAtZero.backoffWithJitter(base, attempt)).not.toBe(400);
    expect(policyAtOne.backoffWithJitter(base, attempt)).not.toBe(400);
  });

  it("retries on transient failure with jittered delay", async () => {
    let attempts = 0;
    const policy = new RetryPolicy(() => 0); // deterministic min spread
    const result = await policy.execute(async () => {
      attempts++;
      if (attempts < 3) throw new Error("transient");
      return "ok";
    }, 3, 1);
    expect(result).toBe("ok");
    expect(attempts).toBe(3);
  });
});
