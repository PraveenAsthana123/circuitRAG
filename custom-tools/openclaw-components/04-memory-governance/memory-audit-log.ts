import { AuditRecord } from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

export interface AuditRecordStore {
  append(record: AuditRecord): void;
  listByMemory(memoryId: string): AuditRecord[];
}

export class InMemoryAuditRecordStore implements AuditRecordStore {
  private readonly auditRecords: AuditRecord[] = [];

  append(record: AuditRecord): void {
    this.auditRecords.push(structuredClone(record));
  }

  listByMemory(memoryId: string): AuditRecord[] {
    return this.auditRecords
      .filter((record) => record.memoryId === memoryId)
      .map((record) => structuredClone(record));
  }

  size(): number {
    return this.auditRecords.length;
  }
}

export class MemoryAuditLog {
  private readonly sink: EventSink;
  private readonly store: AuditRecordStore;

  // Iter 104 (2026-05-18): pluggable append-only store. The local
  // InMemoryAuditRecordStore preserves behavior; production should
  // provide a durable append-only Postgres/SIEM-backed implementation.
  // The sink remains the event-export path, not the canonical store.
  constructor(sink?: EventSink, store?: AuditRecordStore) {
    this.sink = sink ?? new ConsoleEventSink();
    this.store = store ?? new InMemoryAuditRecordStore();
  }

  append(record: AuditRecord): void {
    this.store.append(record);

    this.sink.emit({
      type: "memory_audit",
      ...record,
    });
  }

  listByMemory(memoryId: string): AuditRecord[] {
    return this.store.listByMemory(memoryId);
  }
}
