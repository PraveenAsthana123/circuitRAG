// Negative drills for Iter 18 (2026-05-17): CircuitBreaker
// successThreshold — closing requires N consecutive successes.

import { describe, it, expect } from "vitest";
import { CircuitBreaker } from "./circuit-breaker";
import { ResiliencePolicy } from "./types";

const POLICY_STRICT: ResiliencePolicy = {
  timeoutMs: 100,
  maxRetries: 0,
  retryDelayMs: 1,
  failureThreshold: 2,
  resetAfterMs: 1,
  successThreshold: 3,  // require 3 consecutive successes
};

async function reachHalfOpen(cb: CircuitBreaker): Promise<void> {
  cb.recordFailure();
  cb.recordFailure();
  await new Promise((r) => setTimeout(r, POLICY_STRICT.resetAfterMs + 2));
  // First canExecute() transitions to half_open and admits one probe.
  expect(cb.canExecute()).toBe(true);
}

describe("CircuitBreaker — N consecutive successes to close (P1)", () => {
  it("BACKDOOR CHECK: 1 success at threshold=3 does NOT close", async () => {
    const cb = new CircuitBreaker(POLICY_STRICT);
    await reachHalfOpen(cb);
    cb.recordSuccess();
    expect(cb.getState()).toBe("half_open");
    expect(cb.getSuccessStreak()).toBe(1);
  });

  it("2 successes still half_open", async () => {
    const cb = new CircuitBreaker(POLICY_STRICT);
    await reachHalfOpen(cb);

    cb.recordSuccess();
    expect(cb.canExecute()).toBe(true); // admit next probe
    cb.recordSuccess();

    expect(cb.getState()).toBe("half_open");
    expect(cb.getSuccessStreak()).toBe(2);
  });

  it("3rd consecutive success closes the breaker", async () => {
    const cb = new CircuitBreaker(POLICY_STRICT);
    await reachHalfOpen(cb);

    cb.recordSuccess();
    expect(cb.canExecute()).toBe(true);
    cb.recordSuccess();
    expect(cb.canExecute()).toBe(true);
    cb.recordSuccess();

    expect(cb.getState()).toBe("closed");
    expect(cb.getSuccessStreak()).toBe(0); // reset after close
  });

  it("any failure during the streak re-opens AND resets streak", async () => {
    const cb = new CircuitBreaker(POLICY_STRICT);
    await reachHalfOpen(cb);

    cb.recordSuccess();             // streak = 1
    expect(cb.canExecute()).toBe(true);
    cb.recordFailure();              // streak resets, state → open
    expect(cb.getState()).toBe("open");
    expect(cb.getSuccessStreak()).toBe(0);
  });

  it("default successThreshold = 1 (backcompat with iter 6)", async () => {
    const policyDefault: ResiliencePolicy = {
      timeoutMs: 100,
      maxRetries: 0,
      retryDelayMs: 1,
      failureThreshold: 2,
      resetAfterMs: 1,
      // No successThreshold → default 1.
    };
    const cb = new CircuitBreaker(policyDefault);
    cb.recordFailure(); cb.recordFailure();
    await new Promise((r) => setTimeout(r, 3));
    cb.canExecute(); // half_open + probe admitted
    cb.recordSuccess();
    expect(cb.getState()).toBe("closed"); // single success closes
  });
});
