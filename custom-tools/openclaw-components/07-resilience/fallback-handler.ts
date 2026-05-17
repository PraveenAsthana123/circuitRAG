import { ResilienceContext } from "./types";

export class FallbackHandler {
  async executeFallback<T>(
    context: ResilienceContext,
    fallback?: () => Promise<T>
  ): Promise<T> {
    console.warn(JSON.stringify({
      type: "fallback_triggered",
      requestId: context.requestId,
      sessionId: context.sessionId,
      tenantId: context.tenantId,
      component: context.component,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    }));

    if (!fallback) {
      throw new Error("No fallback available");
    }

    return fallback();
  }
}
