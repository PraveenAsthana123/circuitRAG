export type CircuitState = "closed" | "open" | "half_open";

export interface ResilienceContext {
  requestId: string;
  sessionId: string;
  userId: string;
  tenantId: string;
  traceId: string;
  component: string;
}

export interface ResiliencePolicy {
  timeoutMs: number;
  maxRetries: number;
  retryDelayMs: number;
  failureThreshold: number;
  resetAfterMs: number;
  /**
   * Number of consecutive successes required in half_open before
   * the breaker closes (Iter 18). Default 1 (matches the pre-fix
   * behavior). 3-5 is typical for production.
   */
  successThreshold?: number;
}

export interface ExecutionOutcome<T> {
  success: boolean;
  data?: T;
  fallbackUsed: boolean;
  // When fallbackUsed=true, what source was the fallback drawn from?
  // (Set by FallbackHandler in Iter 13; "unspecified" if the caller
  // didn't tag a tagged fallback.)
  fallbackSource?:
    | "cache"
    | "static"
    | "degraded_model"
    | "stale"
    | "unspecified";
  error?: string;
  durationMs: number;
}
