import { randomUUID } from "crypto";
import { MemoryRecord } from "./types";
import { MemoryStore } from "./memory-store";
import { MemoryAuditLog } from "./memory-audit-log";
import { PIIMasker } from "./pii-masker";
import { RetentionPolicy } from "./retention-policy";
import { ValueEncryptor } from "./encryption";

interface SaveMemoryInput {
  tenantId: string;
  userId: string;
  actorUserId: string;
  key: string;
  value: string;
  reason: string;
  traceId?: string;
  retentionDays?: number;
}

export class MemoryGovernanceService {
  constructor(
    private readonly store: MemoryStore,
    private readonly audit: MemoryAuditLog,
    private readonly piiMasker: PIIMasker,
    private readonly retention: RetentionPolicy,
    // Iter 20: optional encryption-at-rest. If provided, values are
    // encrypted before store + decrypted on read. Backcompat: if
    // omitted, behaves as pre-fix (PII-masked plaintext stored).
    private readonly encryptor?: ValueEncryptor,
  ) {}

  save(input: SaveMemoryInput): MemoryRecord {
    const maskedValue = this.piiMasker.mask(input.value);
    const storedValue = this.encryptor
      ? this.encryptor.encrypt(maskedValue)
      : maskedValue;

    const existing = this.store.findByKey(
      input.tenantId,
      input.userId,
      input.key
    );

    const now = new Date().toISOString();

    const record: MemoryRecord = {
      memoryId: existing?.memoryId ?? randomUUID(),
      tenantId: input.tenantId,
      userId: input.userId,
      scope: "user",
      key: input.key,
      value: storedValue,
      version: existing ? existing.version + 1 : 1,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      expiresAt: input.retentionDays
        ? this.retention.calculateExpiry(input.retentionDays)
        : undefined,
    };

    const saved = this.store.upsert(record);

    this.audit.append({
      auditId: randomUUID(),
      memoryId: saved.memoryId,
      action: existing ? "update" : "create",
      actorUserId: input.actorUserId,
      tenantId: input.tenantId,
      previousValue: existing?.value,
      newValue: saved.value,
      reason: input.reason,
      traceId: input.traceId,
      timestamp: now,
    });

    return saved;
  }

  read(tenantId: string, userId: string, key: string): MemoryRecord | undefined {
    const record = this.store.findByKey(tenantId, userId, key);

    if (!record) return undefined;

    if (this.retention.isExpired(record)) {
      this.store.delete(record.memoryId, record.tenantId);
      return undefined;
    }

    // Decrypt on read. If encryptor is not configured but record was
    // encrypted (e.g., after a deploy that dropped the encryptor),
    // the sentinel-prefixed value is returned as-is — the caller will
    // see garbage and should escalate.
    if (this.encryptor) {
      return { ...record, value: this.encryptor.decrypt(record.value) };
    }
    return record;
  }

  rollback(
    memoryId: string,
    callerTenantId: string,
    actorUserId: string,
    reason: string,
    traceId?: string,
  ): MemoryRecord {
    // store.get + rollback both enforce tenant; AccessDenied bubbles up.
    const before = this.store.get(memoryId, callerTenantId);
    const restored = this.store.rollback(memoryId, callerTenantId);

    this.audit.append({
      auditId: randomUUID(),
      memoryId,
      action: "rollback",
      actorUserId,
      tenantId: restored.tenantId,
      previousValue: before?.value,
      newValue: restored.value,
      reason,
      traceId,
      timestamp: new Date().toISOString(),
    });

    return restored;
  }
}
