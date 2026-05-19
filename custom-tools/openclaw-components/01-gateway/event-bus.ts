// ⚠️ STUB — this file was named in Component 1's folder layout but
//     NO source code was provided. Replace with real source when
//     available. See ../GAPS.md (Component 1 row).
//
//     This minimal in-process bus exists only so other code that
//     imports `EventBus` resolves. Production needs a real broker
//     (Kafka / NATS / Redis Streams) with consumer groups, DLQ,
//     and per-tenant partitioning per CLAUDE.md §41.5.

import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export type EventHandler<T = unknown> = (event: T) => void | Promise<void>;

export class EventBus {
  private readonly handlers = new Map<string, EventHandler[]>();
  private readonly sink: EventSink;

  // Iter 103 (2026-05-18): pluggable sink for event_published
  // emissions. Default ConsoleEventSink preserves backcompat.
  constructor(sink?: EventSink) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  on<T = unknown>(eventType: string, handler: EventHandler<T>): void {
    const list = this.handlers.get(eventType) ?? [];
    list.push(handler as EventHandler);
    this.handlers.set(eventType, list);
  }

  async publish<T = unknown>(eventType: string, payload: T): Promise<void> {
    const list = this.handlers.get(eventType) ?? [];

    this.sink.emit({
      type: "event_published",
      eventType,
      handlerCount: list.length,
      timestamp: new Date().toISOString(),
    });

    await Promise.all(list.map((handler) => handler(payload)));
  }
}
