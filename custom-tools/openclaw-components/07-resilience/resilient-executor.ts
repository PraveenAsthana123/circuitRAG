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
import {
  EventSink,
  StreamRoutedEventSink,
} from "../06-observability/sinks";

/**
 * Optional dependencies for ResilientExecutor. Iter 32 (2026-05-17):
 * factored out so callers + tests can inject mocks/spies, and so
 * a custom RetryPolicy (e.g., one with a deterministic randomFn)
 * can be passed in for repeatability. Pre-fix these were `new`'d
 * inline at field-init, which made the class untestable in
 * isolation and tightly coupled to the concrete classes.
 */
export interface ResilientExecutorDeps {
  timeout?: Timeout;
  retry?: RetryPolicy;
  fallbackHandler?: FallbackHandler;
  /** Iter 102 (2026-05-18): pluggable sink for resilience_success
   *  (log stream) + resilience_failure (error stream) emissions.
   *  Default StreamRoutedEventSink preserves the multi-stream
   *  contract iter 90's drill spies on. A future SentrySink /
   *  DatadogSink plugs in unchanged. */
  sink?: EventSink;
}

export class ResilientExecutor {
  private readonly timeout: Timeout;
  private readonly retry: RetryPolicy;
  private readonly fallbackHandler: FallbackHandler;
  private readonly sink: EventSink;

  constructor(
    private readonly circuitBreaker: CircuitBreaker,
    private readonly policy: ResiliencePolicy,
    deps: ResilientExecutorDeps = {},
  ) {
    this.timeout = deps.timeout ?? new Timeout();
    this.retry = deps.retry ?? new RetryPolicy();
    this.fallbackHandler = deps.fallbackHandler ?? new FallbackHandler();
    this.sink = deps.sink ?? new StreamRoutedEventSink();
  }

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

      this.sink.emit({
        _stream: "log",
        type: "resilience_success",
        requestId: context.requestId,
        component: context.component,
        circuitState: this.circuitBreaker.getState(),
        durationMs: Date.now() - start,
        traceId: context.traceId,
        timestamp: new Date().toISOString(),
      });

      return {
        success: true,
        data,
        fallbackUsed: false,
        durationMs: Date.now() - start,
      };
    } catch (error) {
      this.circuitBreaker.recordFailure();

      this.sink.emit({
        _stream: "error",
        type: "resilience_failure",
        requestId: context.requestId,
        component: context.component,
        circuitState: this.circuitBreaker.getState(),
        error: error instanceof Error ? error.message : "Unknown error",
        durationMs: Date.now() - start,
        traceId: context.traceId,
        timestamp: new Date().toISOString(),
      });

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
