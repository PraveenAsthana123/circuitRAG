import { AuditRecord } from "./types";

export class MemoryAuditLog {
  private readonly auditRecords: AuditRecord[] = [];

  append(record: AuditRecord): void {
    this.auditRecords.push(record);

    console.log(JSON.stringify({
      type: "memory_audit",
      ...record,
    }));
  }

  listByMemory(memoryId: string): AuditRecord[] {
    return this.auditRecords.filter((r) => r.memoryId === memoryId);
  }
}
