// Negative drills for Iter 62 (2026-05-17): MemoryGovernanceService
// cross-tenant write/read defense at the service boundary.
//
// Closes GAPS.md Component 4 P0:
//   "No tenant isolation enforcement — caller can pass any tenantId"
//
// Iter 15 added tenant-isolation to MemoryStore (get/delete/rollback).
// This iter closes the SERVICE-LEVEL hole: save() and read() trusted
// the body-claimed tenantId. Now both accept an optional
// `callerTenantId` (the auth-context tenant); when present and !=
// body-claimed tenantId, the call throws BEFORE any persistence /
// retrieval.
//
// Negative assertions:
//   1. save() with callerTenantId != tenantId → throws
//      (no store write, no audit row written)
//   2. read() with callerTenantId != tenantId → throws
//      (no store read; existing memory NOT leaked across tenants)
//   3. Audit log is NOT polluted with the rejected tenant's identity
//      (otherwise an attacker can probe tenant-existence by reading
//       audit log)
//   4. Existing same-tenant flow still works (backcompat)
//   5. Backcompat: omitting callerTenantId defaults to body tenantId
//      (no pre-iter-62 callers broken)
//   6. read() with callerTenantId == tenantId returns the record
//      (regression guard)
//   7. save with cross-tenant claim throws even when the value would
//      have passed all OTHER guards (PII, injection, etc) — boundary
//      check is FIRST

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
  const svc = new MemoryGovernanceService(
    store, audit, new PIIMasker(), new RetentionPolicy(),
  );
  return { svc, store, audit };
}

const BASE = {
  userId: "user-1",
  actorUserId: "actor-1",
  key: "pref-language",
  value: "TypeScript",
  reason: "user preference",
};

describe("Iter 62 — MemoryGovernanceService cross-tenant defense (P0)", () => {
  it("BACKDOOR: save() rejects when callerTenantId != body tenantId", () => {
    const { svc, store, audit } = newService();
    expect(() => svc.save({
      ...BASE,
      tenantId: "tenant-victim",          // body-claimed
      callerTenantId: "tenant-attacker",  // auth-context
    })).toThrow(MemoryAccessDeniedError);

    // No write to either tenant.
    expect(store.findByKey("tenant-victim", BASE.userId, BASE.key)).toBeUndefined();
    expect(store.findByKey("tenant-attacker", BASE.userId, BASE.key)).toBeUndefined();

    // No audit row written — leaking the attempted access via the
    // audit log would itself be a tenant-existence probe channel.
    // (audit log API surface is listByMemory(memoryId); the rejection
    // path uses memoryId "(rejected)" for injection-block, but the
    // tenant-mismatch path writes NOTHING — confirm by checking both
    // possible memory-ids.)
    expect(audit.listByMemory("(rejected)").length).toBe(0);
    expect(audit.listByMemory("(unknown)").length).toBe(0);
  });

  it("BACKDOOR: read() rejects when callerTenantId != target tenantId", () => {
    const { svc, store } = newService();
    // Seed legit data for tenant-A.
    svc.save({
      ...BASE,
      tenantId: "tenant-A",
      callerTenantId: "tenant-A",
    });
    expect(store.findByKey("tenant-A", BASE.userId, BASE.key)).toBeDefined();

    // Attacker authenticated as tenant-B tries to read tenant-A's memory.
    expect(() => svc.read("tenant-A", BASE.userId, BASE.key, "tenant-B"))
      .toThrow(MemoryAccessDeniedError);
  });

  it("same-tenant save() still works (backcompat regression guard)", () => {
    const { svc } = newService();
    const saved = svc.save({
      ...BASE,
      tenantId: "tenant-1",
      callerTenantId: "tenant-1",
    });
    expect(saved.tenantId).toBe("tenant-1");
    expect(saved.key).toBe(BASE.key);
  });

  it("same-tenant read() returns the record (regression guard)", () => {
    const { svc } = newService();
    svc.save({
      ...BASE,
      tenantId: "tenant-1",
      callerTenantId: "tenant-1",
    });
    const r = svc.read("tenant-1", BASE.userId, BASE.key, "tenant-1");
    expect(r).toBeDefined();
    expect(r!.value).toBe("TypeScript");
  });

  it("BACKCOMPAT: omitting callerTenantId defaults to body tenantId (pre-iter-62 callers unaffected)", () => {
    const { svc } = newService();
    // No callerTenantId passed — pre-iter-62 behavior preserved.
    const saved = svc.save({
      ...BASE,
      tenantId: "tenant-legacy",
    });
    expect(saved.tenantId).toBe("tenant-legacy");
    // And read also works without callerTenantId.
    const r = svc.read("tenant-legacy", BASE.userId, BASE.key);
    expect(r).toBeDefined();
  });

  it("cross-tenant save() throws BEFORE the value reaches PII / injection / encryption pipeline", () => {
    // Use a benign value so we know the throw is from the tenant check
    // (not from a PII or injection rule).
    const { svc, store } = newService();
    expect(() => svc.save({
      ...BASE,
      value: "totally benign content",
      tenantId: "tenant-victim",
      callerTenantId: "tenant-attacker",
    })).toThrow(MemoryAccessDeniedError);
    // Confirm no work was done.
    expect(store.findByKey("tenant-victim", BASE.userId, BASE.key)).toBeUndefined();
  });

  it("cross-tenant read() throws even when target memory does NOT exist (no existence probe)", () => {
    // An attacker should not be able to differentiate "memory exists
    // for other tenant but I can't read it" from "memory does not
    // exist for any tenant". Both must throw the same way for the
    // cross-tenant case.
    const { svc } = newService();
    // No data seeded.
    expect(() => svc.read("tenant-X", "user-Z", "nonexistent-key", "tenant-Y"))
      .toThrow(MemoryAccessDeniedError);
  });

  it("attacker cannot OVERWRITE an existing same-tenant memory via cross-tenant save", () => {
    const { svc, store } = newService();
    // Legit save for tenant-1.
    svc.save({
      ...BASE,
      tenantId: "tenant-1",
      callerTenantId: "tenant-1",
      value: "original",
    });

    // Attacker authenticated as tenant-2 tries to overwrite.
    expect(() => svc.save({
      ...BASE,
      tenantId: "tenant-1",  // forged
      callerTenantId: "tenant-2",  // real auth context
      value: "POISONED",
    })).toThrow(MemoryAccessDeniedError);

    // Original value preserved.
    const r = store.findByKey("tenant-1", BASE.userId, BASE.key);
    expect(r!.value).toBe("original");
  });
});
