import { CircuitState, ResiliencePolicy } from "./types";

export class CircuitBreaker {
  private state: CircuitState = "closed";
  private failureCount = 0;
  private lastFailureAt = 0;

  constructor(private readonly policy: ResiliencePolicy) {}

  canExecute(): boolean {
    if (this.state === "closed") return true;

    if (this.state === "open") {
      const elapsed = Date.now() - this.lastFailureAt;

      if (elapsed >= this.policy.resetAfterMs) {
        this.state = "half_open";
        return true;
      }

      return false;
    }

    return true;
  }

  recordSuccess(): void {
    this.failureCount = 0;
    this.state = "closed";
  }

  recordFailure(): void {
    this.failureCount += 1;
    this.lastFailureAt = Date.now();

    if (this.failureCount >= this.policy.failureThreshold) {
      this.state = "open";
    }
  }

  getState(): CircuitState {
    return this.state;
  }
}
