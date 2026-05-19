import {
  EventSink,
  StreamRoutedEventSink,
} from "../06-observability/sinks";

export class Logger {
  private readonly sink: EventSink;
  // Iter 101 (2026-05-18): pluggable sink. Component 3 Logger uses
  // an uppercase-level shape (INFO/WARN/ERROR) distinct from
  // Component 6 StructuredLogger's lowercase enum, so it can't
  // share LogSink directly. Instead reuses EventSink + the
  // StreamRoutedEventSink _stream hint pattern (iter 99) to
  // preserve console.log/warn/error routing.
  constructor(sink?: EventSink) {
    this.sink = sink ?? new StreamRoutedEventSink();
  }

  info(message: string, meta: Record<string, unknown> = {}) {
    this.sink.emit({
      _stream: "log",
      level: "INFO",
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    });
  }

  warn(message: string, meta: Record<string, unknown> = {}) {
    this.sink.emit({
      _stream: "warn",
      level: "WARN",
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    });
  }

  error(message: string, meta: Record<string, unknown> = {}) {
    this.sink.emit({
      _stream: "error",
      level: "ERROR",
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    });
  }
}
