// Iter 106 (2026-05-18): unify Component 3's bespoke ToolTelemetry*
// types with the canonical Component 6 EventSink (M2.3) + its
// in-memory/console adapters. ToolTelemetrySink was structurally
// identical to EventSink (both `emit(opaque-record-map)`); maintaining
// a parallel interface added cognitive overhead without value.
//
// Backcompat preserved: the old class/interface names remain
// exported as aliases, so any caller importing
// `ToolTelemetrySink` / `ConsoleToolTelemetrySink` / `InMemory-
// ToolTelemetrySink` / `ToolTelemetryRecord` still works.

import {
  EventRecord,
  EventSink,
  ConsoleEventSink,
  InMemoryEventSink,
} from "../06-observability/sinks";

// Canonical aliases — preferred names for new code.
export type ToolTelemetryRecord = EventRecord;
export type ToolTelemetrySink = EventSink;

// Backcompat class aliases — existing imports keep working.
// (`class X = Y` isn't valid; re-export via subclass with empty body.)
export class ConsoleToolTelemetrySink extends ConsoleEventSink {}
export class InMemoryToolTelemetrySink extends InMemoryEventSink {}

export class Telemetry {
  constructor(private readonly sink: ToolTelemetrySink = new ConsoleToolTelemetrySink()) {}

  startSpan(name: string, attributes: Record<string, unknown>) {
    const startTime = Date.now();

    return {
      end: (extra: Record<string, unknown> = {}) => {
        const durationMs = Date.now() - startTime;

        this.sink.emit({
          type: "trace",
          span: name,
          durationMs,
          timestamp: new Date().toISOString(),
          attributes,
          extra,
        });
      },
    };
  }

  recordMetric(name: string, value: number, tags: Record<string, string>) {
    this.sink.emit({
      type: "metric",
      name,
      value,
      tags,
      timestamp: new Date().toISOString(),
    });
  }
}
