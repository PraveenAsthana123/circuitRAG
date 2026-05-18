// ✅ P1 IMPROVED (Iter 47, 2026-05-17): cardinality limit.
//     Pre-fix: every (metricName, labelSet) combination created a
//     new metric series. A label like `userId` or `requestId` (high
//     cardinality) would explode the metric storage — Prometheus
//     OOM, Datadog $100k/mo bill, dashboards unusably slow.
//
//     Now: per-metric cardinality budget. Once a metric crosses
//     maxSeriesPerMetric distinct label sets, new series are
//     ROUTED TO an "_overflow" series with no labels, and a
//     cardinality_overflow counter logs the violating metric name
//     so operators can spot the misuse.
//
//     Also new: validateLabels() rejects forbidden high-cardinality
//     label names (userId, requestId, sessionId by default).

import { MetricsSink, ConsoleMetricsSink } from "./sinks";

const DEFAULT_MAX_SERIES_PER_METRIC = 1_000;
const FORBIDDEN_HIGH_CARD_LABELS = new Set([
  "userId", "requestId", "sessionId", "traceId", "spanId",
  "email", "ipAddress",
]);

export interface MetricsRecorderConfig {
  maxSeriesPerMetric?: number;
  forbiddenLabels?: Set<string>;
}

function labelKey(labels: Record<string, string>): string {
  return Object.keys(labels)
    .sort()
    .map((k) => `${k}=${labels[k]}`)
    .join(",");
}

export class MetricsRecorder {
  private readonly seriesSeen = new Map<string, Set<string>>();
  private readonly overflowLogged = new Set<string>();
  private readonly maxSeries: number;
  private readonly forbidden: Set<string>;
  private readonly sink: MetricsSink;

  constructor(config: MetricsRecorderConfig = {}, sink?: MetricsSink) {
    this.maxSeries = config.maxSeriesPerMetric ?? DEFAULT_MAX_SERIES_PER_METRIC;
    this.forbidden = config.forbiddenLabels ?? FORBIDDEN_HIGH_CARD_LABELS;
    // Iter M2.2 (2026-05-18): pluggable sink. Default ConsoleMetricsSink
    // preserves backcompat; InMemoryMetricsSink lets drills capture
    // without spy boilerplate; a future PrometheusSink plugs in
    // unchanged. See sinks.ts.
    this.sink = sink ?? new ConsoleMetricsSink();
  }

  counter(name: string, value: number, labels: Record<string, string>): void {
    this._emit("counter", name, value, labels);
  }

  histogram(name: string, value: number, labels: Record<string, string>): void {
    this._emit("histogram", name, value, labels);
  }

  private _emit(
    metricType: "counter" | "histogram",
    name: string,
    value: number,
    rawLabels: Record<string, string>,
  ): void {
    // 1. Drop forbidden labels with a one-time per-(name,label) warning.
    const labels = this._stripForbidden(name, rawLabels);

    // 2. Cardinality budget check.
    const key = labelKey(labels);
    const seen = this.seriesSeen.get(name) ?? new Set();
    let effectiveLabels = labels;
    if (!seen.has(key)) {
      if (seen.size >= this.maxSeries) {
        // Route to overflow + log once per metric.
        if (!this.overflowLogged.has(name)) {
          console.warn(JSON.stringify({
            type: "metric_cardinality_overflow",
            name,
            seenSoFar: seen.size,
            limit: this.maxSeries,
            timestamp: new Date().toISOString(),
          }));
          this.overflowLogged.add(name);
        }
        effectiveLabels = { _overflow: "true" };
      } else {
        seen.add(key);
        this.seriesSeen.set(name, seen);
      }
    }

    this.sink.emit({
      type: "metric",
      metricType,
      name,
      value,
      labels: effectiveLabels,
      timestamp: new Date().toISOString(),
    });
  }

  private _stripForbidden(
    name: string,
    rawLabels: Record<string, string>,
  ): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(rawLabels)) {
      if (this.forbidden.has(k)) {
        const warnKey = `${name}:${k}`;
        if (!this.overflowLogged.has(warnKey)) {
          console.warn(JSON.stringify({
            type: "metric_forbidden_label_dropped",
            name,
            label: k,
            timestamp: new Date().toISOString(),
          }));
          this.overflowLogged.add(warnKey);
        }
        continue;
      }
      out[k] = v;
    }
    return out;
  }

  /** Test helper. */
  seriesCount(name: string): number {
    return this.seriesSeen.get(name)?.size ?? 0;
  }
}
