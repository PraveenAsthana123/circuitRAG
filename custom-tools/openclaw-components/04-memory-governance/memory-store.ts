import { MemoryRecord } from "./types";

export class MemoryStore {
  private readonly records = new Map<string, MemoryRecord>();
  private readonly history = new Map<string, MemoryRecord[]>();

  upsert(record: MemoryRecord): MemoryRecord {
    const existing = this.records.get(record.memoryId);

    if (existing) {
      const oldHistory = this.history.get(record.memoryId) ?? [];
      oldHistory.push({ ...existing });
      this.history.set(record.memoryId, oldHistory);
    }

    this.records.set(record.memoryId, record);
    return record;
  }

  get(memoryId: string): MemoryRecord | undefined {
    return this.records.get(memoryId);
  }

  findByKey(tenantId: string, userId: string, key: string): MemoryRecord | undefined {
    return Array.from(this.records.values()).find(
      (r) => r.tenantId === tenantId && r.userId === userId && r.key === key
    );
  }

  rollback(memoryId: string): MemoryRecord {
    const versions = this.history.get(memoryId) ?? [];

    const previous = versions.pop();

    if (!previous) {
      throw new Error("No previous memory version available for rollback");
    }

    this.records.set(memoryId, previous);
    this.history.set(memoryId, versions);

    return previous;
  }

  delete(memoryId: string): void {
    this.records.delete(memoryId);
  }
}
