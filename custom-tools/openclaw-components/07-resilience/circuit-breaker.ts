// ✅ P0 FIXED (Iter 6, 2026-05-17): half-open race closed via
//     halfOpenProbeInFlight flag.
// ✅ P1 FIXED (Iter 18, 2026-05-17): closing requires N consecutive
//     successes in half-open. Pre-fix: a single successful probe
//     flipped the breaker straight to closed — letting it eagerly
//     re-saturate a downstream that hadn't actually recovered.
//
//     Default successThreshold = 1 (backcompat). Set 3-5 in
//     production via ResiliencePolicy.successThreshold.

import { CircuitState, ResiliencePolicy } from "./types";

export class CircuitBreaker {
  private state: CircuitState = "closed";
  private failureCount = 0;
  private lastFailureAt = 0;
  private halfOpenProbeInFlight = false;
  private halfOpenSuccessStreak = 0;

  constructor(private readonly policy: ResiliencePolicy) {}

  private get successThreshold(): number {
    return Math.max(1, this.policy.successThreshold ?? 1);
  }

  canExecute(): boolean {
    if (this.state === "closed") return true;

    if (this.state === "open") {
      const elapsed = Date.now() - this.lastFailureAt;
      if (elapsed >= this.policy.resetAfterMs) {
        this.state = "half_open";
        this.halfOpenSuccessStreak = 0;
        this.halfOpenProbeInFlight = true;
        return true;
      }
      return false;
    }

    // half_open: admit one probe at a time.
    if (this.halfOpenProbeInFlight) return false;
    this.halfOpenProbeInFlight = true;
    return true;
  }

  recordSuccess(): void {
    if (this.state === "half_open") {
      this.halfOpenSuccessStreak += 1;
      this.halfOpenProbeInFlight = false;
      if (this.halfOpenSuccessStreak >= this.successThreshold) {
        // Sustained recovery — close.
        this.state = "closed";
        this.failureCount = 0;
        this.halfOpenSuccessStreak = 0;
      }
      // Else: stay half_open and await more probes.
      return;
    }

    // closed (normal path): reset failure count.
    this.failureCount = 0;
    this.halfOpenProbeInFlight = false;
  }

  recordFailure(): void {
    this.lastFailureAt = Date.now();
    this.halfOpenProbeInFlight = false;

    if (this.state === "half_open") {
      // Any failure in half_open re-opens immediately and resets streak.
      this.state = "open";
      this.halfOpenSuccessStreak = 0;
      return;
    }

    this.failureCount += 1;
    if (this.failureCount >= this.policy.failureThreshold) {
      this.state = "open";
    }
  }

  getState(): CircuitState {
    return this.state;
  }

  /** Test helper. */
  getSuccessStreak(): number {
    return this.halfOpenSuccessStreak;
  }
}
