import { describe, expect, it } from "vitest";
import { InMemoryEventSink } from "../06-observability/sinks";
import {
  AuditRecordStore,
  InMemoryAuditRecordStore,
  MemoryAuditLog,
} from "./memory-audit-log";
import { AuditRecord } from "./types";

function auditRecord(memoryId = "m-1", action: AuditRecord["action"] = "create"): AuditRecord {
  return {
    auditId: `a-${memoryId}-${action}`,
    memoryId,
    action,
    actorUserId: "u-1",
    tenantId: "t-1",
    newValue: "v",
    reason: "test",
    traceId: "tr-1",
    timestamp: "2026-05-18T00:00:00.000Z",
  };
}

class SpyAuditRecordStore implements AuditRecordStore {
  readonly appended: AuditRecord[] = [];
  private readonly delegate = new InMemoryAuditRecordStore();

  append(record: AuditRecord): void {
    this.appended.push(structuredClone(record));
    this.delegate.append(record);
  }

  listByMemory(memoryId: string): AuditRecord[] {
    return this.delegate.listByMemory(memoryId);
  }
}

describe("MemoryAuditLog append-only store seam", () => {
  it("persists audit rows through the injected record store", () => {
    const sink = new InMemoryEventSink();
    const store = new SpyAuditRecordStore();
    const audit = new MemoryAuditLog(sink, store);

    audit.append(auditRecord("m-1", "create"));
    audit.append(auditRecord("m-1", "delete"));

    expect(store.appended.map((row) => row.action)).toEqual(["create", "delete"]);
    expect(audit.listByMemory("m-1").map((row) => row.action)).toEqual(["create", "delete"]);
  });

  it("emits memory_audit events separately from canonical storage", () => {
    const sink = new InMemoryEventSink();
    const store = new SpyAuditRecordStore();
    const audit = new MemoryAuditLog(sink, store);

    audit.append(auditRecord("m-2", "update"));

    expect(store.appended).toHaveLength(1);
    expect(sink.list()).toMatchObject([
      { type: "memory_audit", memoryId: "m-2", action: "update" },
    ]);
  });

  it("default in-memory store keeps defensive copies", () => {
    const audit = new MemoryAuditLog(new InMemoryEventSink());
    const row = auditRecord("m-3", "create");
    audit.append(row);

    row.newValue = "mutated-after-append";
    const read = audit.listByMemory("m-3");
    read[0].newValue = "mutated-after-read";

    expect(audit.listByMemory("m-3")[0].newValue).toBe("v");
  });

  it("can reuse the same store across MemoryAuditLog construction", () => {
    const store = new InMemoryAuditRecordStore();
    const first = new MemoryAuditLog(new InMemoryEventSink(), store);
    first.append(auditRecord("m-4", "create"));

    const restarted = new MemoryAuditLog(new InMemoryEventSink(), store);

    expect(restarted.listByMemory("m-4")).toHaveLength(1);
    expect(store.size()).toBe(1);
  });
});
