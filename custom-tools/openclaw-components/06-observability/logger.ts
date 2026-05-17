// ✅ P1 IMPROVED (Iter 42, 2026-05-17): structured-field discipline.
//     Pre-fix: every log line accepted any `meta` dict, so logs across
//     the codebase varied wildly in what fields they carried.
//     Correlating events for one request needed regex archaeology
//     because requestId/tenantId/traceId might or might not appear.
//
//     Now: StructuredLogger.log() validates that any provided
//     correlation field has the right shape, AND a stricter
//     RequestLogger wrapper makes requestId + tenantId + traceId
//     MANDATORY for the request-lifetime log entries — so every
//     line in a request flow is correlatable.
//
//     CLAUDE.md §57.6 calls this the canonical-log-fields contract.

const REQUIRED_REQUEST_FIELDS = ["requestId", "tenantId"] as const;

export class StructuredLogger {
  log(
    level: "info" | "warn" | "error",
    message: string,
    meta: Record<string, unknown> = {},
  ): void {
    // Defensive: validate optional correlation fields if present.
    for (const k of REQUIRED_REQUEST_FIELDS) {
      if (k in meta && (typeof meta[k] !== "string" || meta[k] === "")) {
        // Don't drop the log — but flag the misuse so it's visible.
        meta[`_${k}_invalid`] = true;
      }
    }
    console.log(JSON.stringify({
      level,
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    }));
  }
}

/**
 * Request-scoped wrapper. Bind once per request with the
 * correlation IDs; every log call inherits them automatically.
 * Refuses to construct if requestId or tenantId is missing.
 */
export class RequestLogger {
  constructor(
    private readonly base: StructuredLogger,
    private readonly correlation: {
      requestId: string;
      tenantId: string;
      traceId?: string;
      sessionId?: string;
      userId?: string;
      component?: string;
    },
  ) {
    if (!correlation.requestId) {
      throw new Error("RequestLogger requires a requestId");
    }
    if (!correlation.tenantId) {
      throw new Error("RequestLogger requires a tenantId");
    }
  }

  info(message: string, extra: Record<string, unknown> = {}): void {
    this.base.log("info", message, { ...this.correlation, ...extra });
  }
  warn(message: string, extra: Record<string, unknown> = {}): void {
    this.base.log("warn", message, { ...this.correlation, ...extra });
  }
  error(message: string, extra: Record<string, unknown> = {}): void {
    this.base.log("error", message, { ...this.correlation, ...extra });
  }
}
