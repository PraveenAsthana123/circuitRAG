// ✅ P1 FIXED (Iter 13, 2026-05-17): fallback now carries a tag
//     identifying the source. Pre-fix: every fallback looked identical
//     in observability — operators couldn't tell whether they were
//     serving cached responses, static defaults, or degraded models.
//     Now: fallback_source is logged + returned in the outcome.

import { ResilienceContext } from "./types";

export type FallbackSource =
  | "cache"           // pre-computed response from cache
  | "static"          // hard-coded fallback (e.g. "service unavailable")
  | "degraded_model"  // a cheaper/older model
  | "stale"           // last-known-good result
  | "unspecified";    // caller didn't tag — legacy or test

export interface FallbackResult<T> {
  data: T;
  source: FallbackSource;
}

export type TaggedFallback<T> = () => Promise<FallbackResult<T>>;
export type SimpleFallback<T> = () => Promise<T>;

export class FallbackHandler {
  async executeFallback<T>(
    context: ResilienceContext,
    fallback?: TaggedFallback<T> | SimpleFallback<T>,
  ): Promise<FallbackResult<T>> {
    if (!fallback) {
      console.warn(JSON.stringify({
        type: "fallback_unavailable",
        requestId: context.requestId,
        component: context.component,
        traceId: context.traceId,
        timestamp: new Date().toISOString(),
      }));
      throw new Error("No fallback available");
    }

    const raw = await fallback();
    const tagged: FallbackResult<T> = this.normalize(raw);

    console.warn(JSON.stringify({
      type: "fallback_triggered",
      requestId: context.requestId,
      sessionId: context.sessionId,
      tenantId: context.tenantId,
      component: context.component,
      fallbackSource: tagged.source,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    }));

    return tagged;
  }

  private normalize<T>(raw: T | FallbackResult<T>): FallbackResult<T> {
    if (
      raw !== null &&
      typeof raw === "object" &&
      "source" in (raw as object) &&
      "data" in (raw as object)
    ) {
      return raw as FallbackResult<T>;
    }
    return { data: raw as T, source: "unspecified" };
  }
}
