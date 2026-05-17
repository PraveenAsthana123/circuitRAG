// ✅ P1 FIXED (2026-05-17): retry backoff now includes jitter.
//     Pre-fix: delay was `delayMs * 2^attempt` exactly — every client
//     that failed at the same instant would retry at the same instant,
//     causing thundering-herd amplification against the downstream
//     that was already struggling.
//
//     Now: delay is `delayMs * 2^attempt * (0.5 + Math.random())` —
//     "full jitter" pattern (AWS Architecture Blog, "Exponential
//     Backoff And Jitter"). Spreads retries across a window so a
//     correlated failure doesn't recreate the original load spike.
//
//     Constructor accepts an optional `randomFn` so tests can pin
//     it to a deterministic value.

export class RetryPolicy {
  constructor(private readonly randomFn: () => number = Math.random) {}

  async execute<T>(
    operation: () => Promise<T>,
    maxRetries: number,
    delayMs: number
  ): Promise<T> {
    let lastError: unknown;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error;

        if (attempt < maxRetries) {
          await this.sleep(this.backoffWithJitter(delayMs, attempt));
        }
      }
    }

    throw lastError;
  }

  /**
   * Public for testing only. Returns ms to wait before the next attempt.
   * Full-jitter: base = delayMs * 2^attempt; actual = base * (0.5 + r)
   * where r ∈ [0, 1). Spread is roughly [base/2, 3*base/2).
   */
  backoffWithJitter(delayMs: number, attempt: number): number {
    const base = delayMs * Math.pow(2, attempt);
    return Math.floor(base * (0.5 + this.randomFn()));
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
