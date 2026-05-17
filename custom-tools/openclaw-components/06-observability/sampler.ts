// Added Iter 29 (2026-05-17) — sampling strategies for the Tracer.
// Pre-fix the tracer logged EVERY span — fine for an exploration
// app, but production needs probabilistic sampling so high-traffic
// services don't drown in trace data.
//
// "Always-on-error" is the override: regardless of probability,
// any span ending with status='error' is always sampled. Without
// this, low-rate failures vanish from observability.

export interface Sampler {
  /** Called BEFORE the span is opened (sampling decision affects
   *  child spans too in real OTel; this stub just decides whether
   *  to emit this single span). */
  shouldSample(spanName: string, attributes: Record<string, unknown>): boolean;
  /** Called when a span ends with error — sampler may override its
   *  earlier decision and force emission. */
  alwaysSampleOnError(): boolean;
}

/** Emit every span. Default for tests + low-traffic environments. */
export class AlwaysOnSampler implements Sampler {
  shouldSample(): boolean { return true; }
  alwaysSampleOnError(): boolean { return true; }
}

/** Probabilistic head-based sampling. Always emits errors. */
export class ProbabilisticSampler implements Sampler {
  constructor(
    private readonly rate: number = 0.1,
    private readonly randomFn: () => number = Math.random,
  ) {
    if (rate < 0 || rate > 1) throw new Error("rate must be in [0, 1]");
  }
  shouldSample(): boolean { return this.randomFn() < this.rate; }
  alwaysSampleOnError(): boolean { return true; }
}

/** Per-operation rate limit so noisy span names can't dominate. */
export class RateLimitedSampler implements Sampler {
  private readonly counts = new Map<string, number[]>();

  constructor(
    private readonly perSecond: number = 100,
  ) {
    if (perSecond < 0) throw new Error("perSecond must be >= 0");
  }

  shouldSample(spanName: string): boolean {
    const now = Date.now();
    const cutoff = now - 1000;
    const list = (this.counts.get(spanName) ?? []).filter((t) => t >= cutoff);
    if (list.length >= this.perSecond) {
      this.counts.set(spanName, list);
      return false;
    }
    list.push(now);
    this.counts.set(spanName, list);
    return true;
  }

  alwaysSampleOnError(): boolean { return true; }
}
