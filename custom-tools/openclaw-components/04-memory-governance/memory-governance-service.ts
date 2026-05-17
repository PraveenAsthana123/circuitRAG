import { randomUUID } from "crypto";
import { MemoryRecord } from "./types";
import { MemoryStore } from "./memory-store";
import { MemoryAuditLog } from "./memory-audit-log";
import { PIIMasker } from "./pii-masker";
import { RetentionPolicy } from "./retention-policy";
import { ValueEncryptor } from "./encryption";
import { PromptInjectionDetector } from "../05-guardrails/prompt-injection-detector";

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

/** Iter 45: thrown when save() rejects a value that contains
 *  prompt-injection patterns (and injection_policy is "block"). */
export class MemoryInjectionRejectedError extends Error {
  constructor(public readonly patterns: string[]) {
    super(
      `Memory value rejected: contains prompt-injection patterns ` +
      `(${patterns.length})`
    );
    this.name = "MemoryInjectionRejectedError";
  }
}

export interface MemoryGovernanceOptions {
  /** "block" (default): throw MemoryInjectionRejectedError.
   *  "audit": save anyway but record a finding in the audit row. */
  injectionPolicy?: "block" | "audit";
}

export class MemoryGovernanceService {
  private readonly injectionPolicy: "block" | "audit";

  constructor(
    private readonly store: MemoryStore,
    private readonly audit: MemoryAuditLog,
    private readonly piiMasker: PIIMasker,
    private readonly retention: RetentionPolicy,
    private readonly encryptor?: ValueEncryptor,
    // Iter 45: optional prompt-injection detector. If provided,
    // every save() value is scanned. Default policy "block": throws
    // MemoryInjectionRejectedError if any pattern detected. With
    // "audit" the value is still stored but the audit row carries
    // an injection_findings field for forensics.
    //
    // Why memory needs this: an attacker who poisons memory at
    // write-time could later get the contaminated value re-injected
    // into the LLM context via a future RAG/personalization call.
    private readonly injectionDetector?: PromptInjectionDetector,
    options: MemoryGovernanceOptions = {},
  ) {
    this.injectionPolicy = options.injectionPolicy ?? "block";
  }

  save(input: SaveMemoryInput): MemoryRecord {
    // Iter 45: injection check happens BEFORE PII mask + encryption
    // so we see the raw text the user submitted.
    const injectionFindings = this.injectionDetector
      ? this.injectionDetector.detect(input.value)
      : [];

    if (injectionFindings.length > 0 && this.injectionPolicy === "block") {
      const patterns = injectionFindings.map((f) => f.message);
      this.audit.append({
        auditId: randomUUID(),
        memoryId: "(rejected)",
        action: "create",
        actorUserId: input.actorUserId,
        tenantId: input.tenantId,
        previousValue: undefined,
        newValue: undefined,
        reason: input.reason + " — REJECTED: prompt injection",
        traceId: input.traceId,
        timestamp: new Date().toISOString(),
      });
      throw new MemoryInjectionRejectedError(patterns);
    }

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

    const auditReason = injectionFindings.length > 0
      ? `${input.reason} — INJECTION_FLAGGED: ${injectionFindings.length} pattern(s)`
      : input.reason;

    this.audit.append({
      auditId: randomUUID(),
      memoryId: saved.memoryId,
      action: existing ? "update" : "create",
      actorUserId: input.actorUserId,
      tenantId: input.tenantId,
      previousValue: existing?.value,
      newValue: saved.value,
      reason: auditReason,
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
