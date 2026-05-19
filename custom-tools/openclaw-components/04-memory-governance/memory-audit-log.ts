import { AuditRecord } from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export class MemoryAuditLog {
  private readonly auditRecords: AuditRecord[] = [];
  private readonly sink: EventSink;

  // Iter 103 (2026-05-18): pluggable sink. memory_audit events are
  // the canonical §38 audit trail; routing them to a durable store
  // (Postgres append-only) is the production path. ConsoleEventSink
  // default preserves backcompat.
  constructor(sink?: EventSink) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  append(record: AuditRecord): void {
    this.auditRecords.push(record);

    this.sink.emit({
      type: "memory_audit",
      ...record,
    });
  }

  listByMemory(memoryId: string): AuditRecord[] {
    return this.auditRecords.filter((r) => r.memoryId === memoryId);
  }
}
