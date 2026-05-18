// Iter M2 (2026-05-18): observability sink interfaces.
//
// Pre-fix: Tracer / MetricsRecorder / AIOpsEventBus all emitted
// JSON via direct console.log calls — bypassing any test capture,
// any production OTel exporter, any log shipper transform layer.
// To plug in real OTel, every emitter would have had to be rewritten.
//
// Now: emitters take an optional Sink dependency. The default sink
// preserves the console.log contract (backcompat). InMemorySink
// captures emissions for drills + tests so they don't pollute the
// suite output. A future OTelSink / PrometheusSink / KafkaSink
// implements the same interface — no emitter rewrite needed.
//
// Per CLAUDE.md §47 boundary discipline: this is the seam.

export interface SpanRecord {
  type: "trace";
  spanName: string;
  status: "ok" | "error";
  durationMs: number;
  attributes: Record<string, unknown>;
  extra: Record<string, unknown>;
  sampled: boolean;
  sampledOnError: boolean;
  timestamp: string;
}

export interface MetricRecord {
  type: "metric";
  metricType: "counter" | "histogram";
  name: string;
  value: number;
  labels: Record<string, string>;
  timestamp: string;
}

export interface EventRecord {
  // Free-shape — the AIOpsEventBus emits multiple `type` values
  // (aiops_event, aiops_incident_correlated). Sink is opaque to
  // the shape; downstream taxonomies enforce it.
  [key: string]: unknown;
}

export interface TraceSink {
  emit(record: SpanRecord): void;
}

export interface MetricsSink {
  emit(record: MetricRecord): void;
}

export interface EventSink {
  emit(record: EventRecord): void;
}

/**
 * Iter M3.1 (2026-05-18): generic structured log sink for emitters
 * that don't fit the trace/metric/event taxonomy. StructuredLogger
 * uses this; future emitters that just want "send this JSON
 * somewhere" can target it too. Records are opaque maps — the
 * canonical-fields contract is owned by the emitter, not the sink.
 */
export interface LogRecord {
  level: "info" | "warn" | "error";
  message: string;
  timestamp: string;
  [extra: string]: unknown;
}

export interface LogSink {
  emit(record: LogRecord): void;
}

/** Default console-based sink. Single-line JSON for log-shipper safety. */
export class ConsoleTraceSink implements TraceSink {
  emit(record: SpanRecord): void {
    console.log(JSON.stringify(record));
  }
}

export class ConsoleMetricsSink implements MetricsSink {
  emit(record: MetricRecord): void {
    console.log(JSON.stringify(record));
  }
}

export class ConsoleEventSink implements EventSink {
  emit(record: EventRecord): void {
    console.log(JSON.stringify(record));
  }
}

/**
 * Iter 98 (2026-05-18): EventSink that routes to console.error.
 * For emitters whose pre-sink behavior was console.error (e.g.,
 * Gateway gateway_error) and whose existing drills spy on
 * console.error specifically. Preserves the stream-routing
 * contract that log shippers / SIEM rules depend on.
 */
export class ConsoleErrorEventSink implements EventSink {
  emit(record: EventRecord): void {
    console.error(JSON.stringify(record));
  }
}

/** Iter M3.1: console LogSink. Preserves the pre-M3.1 contract
 *  that every log line lands on console.log regardless of level —
 *  existing test spy patterns and log-shipper configs assume this.
 *  A future LevelRoutedConsoleLogSink can route info→log /
 *  warn→warn / error→error when callers opt in; default stays
 *  monoline for backcompat. */
export class ConsoleLogSink implements LogSink {
  emit(record: LogRecord): void {
    console.log(JSON.stringify(record));
  }
}

export class InMemoryLogSink implements LogSink {
  private readonly records: LogRecord[] = [];
  constructor(private readonly maxRecords: number = 10_000) {
    if (maxRecords < 1) throw new Error("maxRecords must be >= 1");
  }
  emit(record: LogRecord): void {
    this.records.push(record);
    while (this.records.length > this.maxRecords) this.records.shift();
  }
  list(): LogRecord[] {
    return this.records.map((r) => ({ ...r }));
  }
  size(): number {
    return this.records.length;
  }
  clear(): void {
    this.records.length = 0;
  }
}

/** In-memory sinks for drills + tests. Bounded to maxRecords by
 *  FIFO eviction so a long-running test process doesn't OOM. */
export class InMemoryTraceSink implements TraceSink {
  private readonly records: SpanRecord[] = [];
  constructor(private readonly maxRecords: number = 10_000) {
    if (maxRecords < 1) throw new Error("maxRecords must be >= 1");
  }
  emit(record: SpanRecord): void {
    this.records.push(record);
    while (this.records.length > this.maxRecords) this.records.shift();
  }
  list(): SpanRecord[] {
    return this.records.map((r) => ({ ...r }));  // defensive copy
  }
  size(): number {
    return this.records.length;
  }
  clear(): void {
    this.records.length = 0;
  }
}

export class InMemoryMetricsSink implements MetricsSink {
  private readonly records: MetricRecord[] = [];
  constructor(private readonly maxRecords: number = 10_000) {
    if (maxRecords < 1) throw new Error("maxRecords must be >= 1");
  }
  emit(record: MetricRecord): void {
    this.records.push(record);
    while (this.records.length > this.maxRecords) this.records.shift();
  }
  list(): MetricRecord[] {
    return this.records.map((r) => ({ ...r }));
  }
  size(): number {
    return this.records.length;
  }
  clear(): void {
    this.records.length = 0;
  }
}

export class InMemoryEventSink implements EventSink {
  private readonly records: EventRecord[] = [];
  constructor(private readonly maxRecords: number = 10_000) {
    if (maxRecords < 1) throw new Error("maxRecords must be >= 1");
  }
  emit(record: EventRecord): void {
    this.records.push(record);
    while (this.records.length > this.maxRecords) this.records.shift();
  }
  list(): EventRecord[] {
    return this.records.map((r) => ({ ...r }));
  }
  size(): number {
    return this.records.length;
  }
  clear(): void {
    this.records.length = 0;
  }
}
