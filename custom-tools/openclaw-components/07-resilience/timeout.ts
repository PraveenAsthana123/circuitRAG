// ✅ P1 FIXED (2026-05-17, Iter 13): Timeout now actually cancels
//     the operation via AbortController. Pre-fix: Promise.race
//     "won" but the underlying operation kept running in the
//     background — leaking sockets, fds, tokens, money. Now the
//     operation receives an AbortSignal it can honor (fetch, axios,
//     anything taking { signal }) and the rejection happens cleanly.
//
//     Operations that ignore the signal still leak. The Timeout
//     class can't force-kill arbitrary code. Document that contract:
//     the operation MUST honor the signal.

const DEFAULT_TIMEOUT_MS = 5_000;

export class TimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`Operation timed out after ${timeoutMs}ms`);
    this.name = "TimeoutError";
  }
}

export class Timeout {
  /**
   * Run `operation(signal)` with a deadline. If the deadline
   * fires first:
   *   - controller.abort() is called (signal becomes aborted)
   *   - returned promise rejects with TimeoutError
   *
   * If `operation` honors the signal, it should reject/cleanup
   * on signal.aborted; otherwise the underlying work keeps
   * running (caller's bug, not ours).
   */
  async run<T>(
    operation: (signal: AbortSignal) => Promise<T>,
    timeoutMs: number = DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    const controller = new AbortController();
    let timer: NodeJS.Timeout | undefined;
    const timeoutPromise = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new TimeoutError(timeoutMs));
      }, timeoutMs);
    });

    try {
      return await Promise.race([operation(controller.signal), timeoutPromise]);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }
}
