// ✅ P0 FIXED (2026-05-17): half-open race condition closed.
//     Pre-fix: when state was "open" and resetAfterMs elapsed,
//     canExecute() returned true and flipped to "half_open" — but
//     EVERY concurrent call did the same thing simultaneously, so
//     instead of admitting a single trial request the breaker
//     admitted all in-flight callers and defeated its own purpose.
//
//     Now: half_open admits only one trial probe at a time. Other
//     callers see half_open and are denied until the probe resolves
//     via recordSuccess()/recordFailure(). recordSuccess() in
//     half_open closes the breaker; recordFailure() re-opens it.
//
//     Drill: ../07-resilience/circuit-breaker.test.ts

import { CircuitState, ResiliencePolicy } from "./types";

export class CircuitBreaker {
  private state: CircuitState = "closed";
  private failureCount = 0;
  private lastFailureAt = 0;
  private halfOpenProbeInFlight = false;

  constructor(private readonly policy: ResiliencePolicy) {}

  canExecute(): boolean {
    if (this.state === "closed") return true;

    if (this.state === "open") {
      const elapsed = Date.now() - this.lastFailureAt;
      if (elapsed >= this.policy.resetAfterMs) {
        // Transition to half_open and admit exactly one probe.
        this.state = "half_open";
        this.halfOpenProbeInFlight = true;
        return true;
      }
      return false;
    }

    // state === "half_open": only the in-flight probe is admitted.
    if (this.halfOpenProbeInFlight) {
      // Another concurrent caller — deny.
      return false;
    }
    // No probe in flight yet (e.g. after a recordSuccess that closed
    // and re-opened) — admit one.
    this.halfOpenProbeInFlight = true;
    return true;
  }

  recordSuccess(): void {
    this.failureCount = 0;
    this.state = "closed";
    this.halfOpenProbeInFlight = false;
  }

  recordFailure(): void {
    this.failureCount += 1;
    this.lastFailureAt = Date.now();
    this.halfOpenProbeInFlight = false;

    if (this.failureCount >= this.policy.failureThreshold) {
      this.state = "open";
    }
  }

  getState(): CircuitState {
    return this.state;
  }
}
