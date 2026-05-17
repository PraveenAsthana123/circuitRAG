// ✅ Iter 15 (2026-05-17): three fixes to Component 4's memory store.
//
//   P0 (GAPS row 5): get() / delete() / rollback() now require
//     callerTenantId and refuse cross-tenant access. New
//     MemoryAccessDeniedError exception.
//
//   P2 (GAPS row 2): findByKey() now uses an index on
//     (tenantId, userId, key) for O(1) lookup instead of O(n) scan.
//
//   P2 (GAPS row 3): rollback() now supports multi-version rollback
//     via the new rollbackToVersion(memoryId, version, callerTenantId)
//     method. The original single-step rollback() still works.

import { MemoryRecord } from "./types";

export class MemoryAccessDeniedError extends Error {
  constructor(memoryId: string, callerTenantId: string) {
    super(
      `Tenant ${callerTenantId} cannot access memory ${memoryId} ` +
      `(owned by a different tenant)`
    );
    this.name = "MemoryAccessDeniedError";
  }
}

export class MemoryNotFoundError extends Error {
  constructor(memoryId: string) {
    super(`Memory not found: ${memoryId}`);
    this.name = "MemoryNotFoundError";
  }
}

export class MemoryStore {
  private readonly records = new Map<string, MemoryRecord>();
  private readonly history = new Map<string, MemoryRecord[]>();
  // Index: (tenantId, userId, key) → memoryId.
  private readonly keyIndex = new Map<string, string>();

  upsert(record: MemoryRecord): MemoryRecord {
    const existing = this.records.get(record.memoryId);

    if (existing) {
      if (existing.tenantId !== record.tenantId) {
        throw new MemoryAccessDeniedError(
          record.memoryId,
          record.tenantId,
        );
      }
      const oldHistory = this.history.get(record.memoryId) ?? [];
      oldHistory.push({ ...existing });
      this.history.set(record.memoryId, oldHistory);
    }

    this.records.set(record.memoryId, record);
    this.keyIndex.set(
      this.indexKey(record.tenantId, record.userId, record.key),
      record.memoryId,
    );
    return record;
  }

  get(memoryId: string, callerTenantId: string): MemoryRecord {
    const record = this.records.get(memoryId);
    if (!record) throw new MemoryNotFoundError(memoryId);
    if (record.tenantId !== callerTenantId) {
      throw new MemoryAccessDeniedError(memoryId, callerTenantId);
    }
    return record;
  }

  findByKey(tenantId: string, userId: string, key: string): MemoryRecord | undefined {
    const memoryId = this.keyIndex.get(this.indexKey(tenantId, userId, key));
    if (memoryId === undefined) return undefined;
    return this.records.get(memoryId);
  }

  /** Single-step rollback (compat with prior API). */
  rollback(memoryId: string, callerTenantId: string): MemoryRecord {
    const current = this.records.get(memoryId);
    if (!current) throw new MemoryNotFoundError(memoryId);
    if (current.tenantId !== callerTenantId) {
      throw new MemoryAccessDeniedError(memoryId, callerTenantId);
    }

    const versions = this.history.get(memoryId) ?? [];
    const previous = versions.pop();
    if (!previous) {
      throw new Error("No previous memory version available for rollback");
    }
    this.records.set(memoryId, previous);
    this.history.set(memoryId, versions);
    return previous;
  }

  /**
   * Roll back to a specific historical version. `version` is the
   * MemoryRecord.version number to restore. Throws if that version
   * is not in history.
   */
  rollbackToVersion(
    memoryId: string,
    targetVersion: number,
    callerTenantId: string,
  ): MemoryRecord {
    const current = this.records.get(memoryId);
    if (!current) throw new MemoryNotFoundError(memoryId);
    if (current.tenantId !== callerTenantId) {
      throw new MemoryAccessDeniedError(memoryId, callerTenantId);
    }

    const versions = this.history.get(memoryId) ?? [];
    const idx = versions.findIndex((v) => v.version === targetVersion);
    if (idx === -1) {
      throw new Error(
        `Memory ${memoryId} has no historical version ${targetVersion}`,
      );
    }
    const target = versions[idx];
    // Discard everything AFTER the target (including current).
    const truncated = versions.slice(0, idx);
    this.records.set(memoryId, target);
    this.history.set(memoryId, truncated);
    return target;
  }

  delete(memoryId: string, callerTenantId: string): void {
    const record = this.records.get(memoryId);
    if (!record) return; // idempotent delete
    if (record.tenantId !== callerTenantId) {
      throw new MemoryAccessDeniedError(memoryId, callerTenantId);
    }
    this.records.delete(memoryId);
    this.history.delete(memoryId);
    this.keyIndex.delete(this.indexKey(record.tenantId, record.userId, record.key));
  }

  private indexKey(tenantId: string, userId: string, key: string): string {
    return `${tenantId}:${userId}:${key}`;
  }
}
