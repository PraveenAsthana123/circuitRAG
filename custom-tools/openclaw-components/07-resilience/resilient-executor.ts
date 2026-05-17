// Updated 2026-05-17 (Iter 13) for upstream signature changes:
//   - Timeout.run now takes (signal) => Promise<T> and cancels via
//     AbortController on deadline. Operation MUST honor the signal.
//   - FallbackHandler.executeFallback returns FallbackResult<T> with
//     a `source` tag; we propagate it into ExecutionOutcome.

import { Timeout } from "./timeout";
import { RetryPolicy } from "./retry-policy";
import { CircuitBreaker } from "./circuit-breaker";
import {
  FallbackHandler,
  SimpleFallback,
  TaggedFallback,
} from "./fallback-handler";
import {
  ExecutionOutcome,
  ResilienceContext,
  ResiliencePolicy,
} from "./types";

export class ResilientExecutor {
  private readonly timeout = new Timeout();
  private readonly retry = new RetryPolicy();
  private readonly fallbackHandler = new FallbackHandler();

  constructor(
    private readonly circuitBreaker: CircuitBreaker,
    private readonly policy: ResiliencePolicy
  ) {}

  async execute<T>(
    context: ResilienceContext,
    operation: (signal: AbortSignal) => Promise<T>,
    fallback?: TaggedFallback<T> | SimpleFallback<T>,
  ): Promise<ExecutionOutcome<T>> {
    const start = Date.now();

    if (!this.circuitBreaker.canExecute()) {
      const fallbackResult = await this.fallbackHandler.executeFallback(
        context,
        fallback,
      );
      return {
        success: true,
        data: fallbackResult.data,
        fallbackUsed: true,
        fallbackSource: fallbackResult.source,
        durationMs: Date.now() - start,
      };
    }

    try {
      const data = await this.retry.execute(
        () => this.timeout.run(operation, this.policy.timeoutMs),
        this.policy.maxRetries,
        this.policy.retryDelayMs
      );

      this.circuitBreaker.recordSuccess();

      console.log(JSON.stringify({
        type: "resilience_success",
        requestId: context.requestId,
        component: context.component,
        circuitState: this.circuitBreaker.getState(),
        durationMs: Date.now() - start,
        traceId: context.traceId,
        timestamp: new Date().toISOString(),
      }));

      return {
        success: true,
        data,
        fallbackUsed: false,
        durationMs: Date.now() - start,
      };
    } catch (error) {
      this.circuitBreaker.recordFailure();

      console.error(JSON.stringify({
        type: "resilience_failure",
        requestId: context.requestId,
        component: context.component,
        circuitState: this.circuitBreaker.getState(),
        error: error instanceof Error ? error.message : "Unknown error",
        durationMs: Date.now() - start,
        traceId: context.traceId,
        timestamp: new Date().toISOString(),
      }));

      try {
        const fallbackResult = await this.fallbackHandler.executeFallback(
          context,
          fallback,
        );
        return {
          success: true,
          data: fallbackResult.data,
          fallbackUsed: true,
          fallbackSource: fallbackResult.source,
          durationMs: Date.now() - start,
        };
      } catch {
        return {
          success: false,
          fallbackUsed: false,
          error: error instanceof Error ? error.message : "Unknown error",
          durationMs: Date.now() - start,
        };
      }
    }
  }
}
