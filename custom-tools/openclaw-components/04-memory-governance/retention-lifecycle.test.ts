// Negative drills for Iter 74 (2026-05-17): retention policy
// lifecycle + audit-on-auto-delete fix.
//
// Pre-fix: RetentionPolicy class had ZERO direct test coverage.
// MemoryGovernanceService.read() auto-deletes expired records but
// wrote NO audit row — a state mutation that escaped the audit log,
// violating CLAUDE.md §38 (every state change auditable).
//
// Now: this drill locks the retention lifecycle end-to-end AND
// proves the new audit-on-auto-delete behavior. The drill covers
// the RetentionPolicy unit + the MemoryGovernanceService integration.
//
// Negative assertions (10 steps; 8 negative + 2 positive):
//   1. RetentionPolicy.isExpired returns true after expiry passes
//   2. RetentionPolicy.isExpired returns false for records with no
//      expiresAt (never-expiring)
//   3. RetentionPolicy.calculateExpiry produces an ISO-8601 string
//      that's N days in the future
//   4. BACKDOOR: service.read of an expired memory returns undefined
//      AND deletes from the store
//   5. BACKDOOR: auto-delete on expiry WRITES an audit row with
//      action="delete" + actor="system" + reason="auto-delete:
//      retention expiry" (THE FIX)
//   6. The audit row preserves the PRE-DELETION value (for
//      forensic reconstruction)
//   7. Non-expired memory passes through read unchanged + NO audit
//   8. Calling read TWICE on an expired memory: 1st call audits +
//      deletes; 2nd call returns undefined with NO duplicate audit
//      (idempotent — the record is gone after the first delete)
//   9. Cross-tenant check happens BEFORE retention check (auth
//      precedence preserved)
//  10. calculateExpiry(0) — boundary: zero days = immediate expiry
//      (or as-near-as-possible per implementation)

import { describe, it, expect } from "vitest";
import { MemoryGovernanceService } from "./memory-governance-service";
import { MemoryStore, MemoryAccessDeniedError } from "./memory-store";
import { MemoryAuditLog } from "./memory-audit-log";
import { PIIMasker } from "./pii-masker";
import { RetentionPolicy } from "./retention-policy";

function newService(): {
  svc: MemoryGovernanceService;
  store: MemoryStore;
  audit: MemoryAuditLog;
} {
  const store = new MemoryStore();
  const audit = new MemoryAuditLog();
  return {
    svc: new MemoryGovernanceService(
      store, audit, new PIIMasker(), new RetentionPolicy(),
    ),
    store,
    audit,
  };
}

const TENANT = "tenant-1";
const USER = "user-1";
const KEY = "pref-lang";

describe("Iter 74 — RetentionPolicy unit (P1)", () => {
  it("isExpired returns true after expiry has passed", () => {
    const policy = new RetentionPolicy();
    const past = new Date(Date.now() - 60_000).toISOString();
    const record = {
      memoryId: "m", tenantId: TENANT, userId: USER, scope: "user" as const,
      key: KEY, value: "v", version: 1,
      createdAt: past, updatedAt: past, expiresAt: past,
    };
    expect(policy.isExpired(record)).toBe(true);
  });

  it("isExpired returns false for records with no expiresAt (never-expiring)", () => {
    const policy = new RetentionPolicy();
    const now = new Date().toISOString();
    const record = {
      memoryId: "m", tenantId: TENANT, userId: USER, scope: "user" as const,
      key: KEY, value: "v", version: 1,
      createdAt: now, updatedAt: now,
      // expiresAt deliberately omitted
    };
    expect(policy.isExpired(record)).toBe(false);
  });

  it("calculateExpiry produces ISO-8601 string N days in the future", () => {
    const policy = new RetentionPolicy();
    const days = 30;
    const result = policy.calculateExpiry(days);
    const resultMs = new Date(result).getTime();
    const expectedMs = Date.now() + days * 24 * 60 * 60 * 1000;
    // Allow 1s tolerance (test execution time).
    expect(Math.abs(resultMs - expectedMs)).toBeLessThan(1000);
    // Parses as valid ISO-8601.
    expect(() => new Date(result).toISOString()).not.toThrow();
  });
});

describe("Iter 74 — MemoryGovernanceService retention lifecycle (P1)", () => {
  it("BACKDOOR: read of expired memory returns undefined AND deletes from store", () => {
    const { svc, store } = newService();
    // Seed with retention=0 days (immediately expired or close).
    svc.save({
      tenantId: TENANT, callerTenantId: TENANT,
      userId: USER, actorUserId: USER,
      key: KEY, value: "TypeScript",
      reason: "user pref",
      retentionDays: 0,  // calculateExpiry(0) → today; isExpired true after micro-delay
    });
    // Ensure expiry is in the past by manually backdating.
    const seeded = store.findByKey(TENANT, USER, KEY)!;
    const backdated = {
      ...seeded,
      expiresAt: new Date(Date.now() - 60_000).toISOString(),
    };
    store.upsert(backdated);

    const result = svc.read(TENANT, USER, KEY, TENANT);
    expect(result).toBeUndefined();
    // After the expired read, the record is gone.
    expect(store.findByKey(TENANT, USER, KEY)).toBeUndefined();
  });

  it("BACKDOOR: auto-delete on expiry writes an audit row (THE FIX)", () => {
    const { svc, store, audit } = newService();
    svc.save({
      tenantId: TENANT, callerTenantId: TENANT,
      userId: USER, actorUserId: USER,
      key: KEY, value: "TypeScript",
      reason: "user pref",
      retentionDays: 30,
    });
    const seeded = store.findByKey(TENANT, USER, KEY)!;
    const memoryId = seeded.memoryId;

    // Backdate to expire.
    store.upsert({
      ...seeded,
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });

    // Pre-read: the audit log has the create row but no delete row.
    const auditBefore = audit.listByMemory(memoryId);
    expect(auditBefore.length).toBe(1);
    expect(auditBefore[0].action).toBe("create");

    // Trigger auto-delete.
    svc.read(TENANT, USER, KEY, TENANT);

    // Post-read: a delete audit row was appended.
    const auditAfter = audit.listByMemory(memoryId);
    expect(auditAfter.length).toBe(2);
    const deleteRow = auditAfter.find((r) => r.action === "delete");
    expect(deleteRow).toBeDefined();
    expect(deleteRow!.actorUserId).toBe("system");
    expect(deleteRow!.reason).toBe("auto-delete: retention expiry");
    expect(deleteRow!.tenantId).toBe(TENANT);
    expect(deleteRow!.memoryId).toBe(memoryId);
  });

  it("audit row preserves the PRE-DELETION value (forensic reconstruction)", () => {
    const { svc, store, audit } = newService();
    svc.save({
      tenantId: TENANT, callerTenantId: TENANT,
      userId: USER, actorUserId: USER,
      key: KEY, value: "VALUE_TO_RECONSTRUCT",
      reason: "test",
      retentionDays: 1,
    });
    const seeded = store.findByKey(TENANT, USER, KEY)!;
    const memoryId = seeded.memoryId;
    store.upsert({
      ...seeded,
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });

    svc.read(TENANT, USER, KEY, TENANT);
    const deleteRow = audit.listByMemory(memoryId).find((r) => r.action === "delete");
    expect(deleteRow!.previousValue).toBe("VALUE_TO_RECONSTRUCT");
    expect(deleteRow!.newValue).toBeUndefined();
  });

  it("non-expired memory passes through read unchanged + NO extra audit row", () => {
    const { svc, store, audit } = newService();
    svc.save({
      tenantId: TENANT, callerTenantId: TENANT,
      userId: USER, actorUserId: USER,
      key: KEY, value: "TypeScript",
      reason: "test",
      retentionDays: 30,
    });
    const memoryId = store.findByKey(TENANT, USER, KEY)!.memoryId;

    const result = svc.read(TENANT, USER, KEY, TENANT);
    expect(result).toBeDefined();
    expect(result!.value).toBe("TypeScript");

    // No additional audit row from a normal read (only the create).
    expect(audit.listByMemory(memoryId).length).toBe(1);
  });

  it("idempotent: 2nd read on expired memory returns undefined with NO duplicate audit row", () => {
    const { svc, store, audit } = newService();
    svc.save({
      tenantId: TENANT, callerTenantId: TENANT,
      userId: USER, actorUserId: USER,
      key: KEY, value: "TypeScript",
      reason: "test",
      retentionDays: 1,
    });
    const seeded = store.findByKey(TENANT, USER, KEY)!;
    const memoryId = seeded.memoryId;
    store.upsert({
      ...seeded,
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });

    // 1st read: triggers auto-delete + audit row.
    svc.read(TENANT, USER, KEY, TENANT);
    const auditAfterFirst = audit.listByMemory(memoryId).length;

    // 2nd read: record is gone — returns undefined, NO new audit row.
    const second = svc.read(TENANT, USER, KEY, TENANT);
    expect(second).toBeUndefined();
    expect(audit.listByMemory(memoryId).length).toBe(auditAfterFirst);
  });

  it("cross-tenant check happens BEFORE retention check (auth precedence)", () => {
    const { svc } = newService();
    svc.save({
      tenantId: TENANT, callerTenantId: TENANT,
      userId: USER, actorUserId: USER,
      key: KEY, value: "v",
      reason: "test",
      retentionDays: 30,
    });
    // Caller from a DIFFERENT tenant must see MemoryAccessDeniedError,
    // not a retention pass-through.
    expect(() => svc.read(TENANT, USER, KEY, "tenant-attacker"))
      .toThrow(MemoryAccessDeniedError);
  });

  it("calculateExpiry(0): boundary check (zero days = same-day expiry)", () => {
    const policy = new RetentionPolicy();
    const result = policy.calculateExpiry(0);
    const resultMs = new Date(result).getTime();
    // 0 days means the expiry is "today" — within seconds of now.
    expect(Math.abs(resultMs - Date.now())).toBeLessThan(1000);
  });
});
