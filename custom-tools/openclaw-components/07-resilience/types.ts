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
}

export interface ExecutionOutcome<T> {
  success: boolean;
  data?: T;
  fallbackUsed: boolean;
  error?: string;
  durationMs: number;
}
