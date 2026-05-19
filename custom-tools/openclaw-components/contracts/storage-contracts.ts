// Iter 120 (2026-05-19): parametrized behavioral contracts for the
// 5 storage interfaces. Existing storage-interface-contracts.test.ts
// asserts METHOD-SHAPE compatibility (method names exist). These
// contracts assert BEHAVIORAL compatibility (version semantics,
// tenant isolation, rollback ordering, defensive copies, idempotent
// delete, etc.) — what a Postgres / Redis adapter MUST satisfy to
// be a drop-in replacement for the in-memory adapter.
//
// Each contract is a function that registers `it(...)` blocks
// inside the caller's describe(...). The factory pattern
// (`make...: () => I`) keeps the contract adapter-agnostic; future
// PostgresMemoryStore + RedisSessionStore call the same functions
// with their factory and pass the SAME assertions.
//
// Per CLAUDE.md §43 (drill: ≥ 3 negative assertions) + §57.7
// (drilled invariants prove the contract, not vibes) + §59.1 MDD
// (the contract IS the model; the adapter is one derivation).
//
// Negative assertions per contract:
//   MemoryStore       — cross-tenant get/rollback/delete (4 negatives)
//   WorkflowStore     — cross-tenant get/rollback + same-id different-tenant save (3 negatives)
//   MemoryAuditLog    — listByMemory filters to requested id only + defensive copy (2 negatives)
//   SessionPersistence — unknown get returns undefined + idempotent delete (2 negatives)

import { it, expect } from "vitest";
import type {
  WorkflowStoreI,
  MemoryStoreI,
  MemoryAuditLogI,
  SessionPersistenceStoreI,
} from "../interfaces";
import type {
  MemoryRecord,
  AuditRecord,
} from "../04-memory-governance/types";
import type {
  WorkflowState,
} from "../10-agent-workflow/types";
import type {
  SessionState,
} from "../01-gateway/types";

function nowIso(): string {
  return new Date().toISOString();
}

/**
 * Returns true if err.name matches expected (without depending on
 * the concrete error class — production adapters must throw with
 * the canonical name, but may use their own subclass hierarchy).
 */
function errName(err: unknown): string {
  if (err && typeof err === "object" && "name" in err) {
    return String((err as { name: unknown }).name);
  }
  return "";
}

// ───────────────────────────── MemoryStore contract ─────────────────────────────

export function runMemoryStoreContract(
  contractName: string,
  makeStore: () => MemoryStoreI,
): void {
  const baseRecord = (overrides: Partial<MemoryRecord> = {}): MemoryRecord => ({
    memoryId: "m-1",
    tenantId: "tenant-A",
    userId: "user-1",
    scope: "user",
    key: "k1",
    value: "v1",
    version: 1,
    createdAt: nowIso(),
    updatedAt: nowIso(),
    ...overrides,
  });

  it(`[${contractName}] BACKDOOR: upsert returns the persisted record`, () => {
    const store = makeStore();
    const result = store.upsert(baseRecord());
    expect(result.memoryId).toBe("m-1");
    expect(result.value).toBe("v1");
  });

  it(`[${contractName}] upsert + get round-trip returns the latest version`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ value: "v1", version: 1 }));
    store.upsert(baseRecord({ value: "v2", version: 2 }));
    expect(store.get("m-1", "tenant-A").value).toBe("v2");
    expect(store.get("m-1", "tenant-A").version).toBe(2);
  });

  it(`[${contractName}] findByKey returns the latest matching record`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ value: "v1", version: 1 }));
    store.upsert(baseRecord({ value: "v2", version: 2 }));
    expect(store.findByKey("tenant-A", "user-1", "k1")?.value).toBe("v2");
  });

  it(`[${contractName}] findByKey returns undefined for unknown key`, () => {
    const store = makeStore();
    expect(store.findByKey("tenant-A", "user-1", "missing")).toBeUndefined();
  });

  it(`[${contractName}] rollback restores the previous version`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ value: "v1", version: 1 }));
    store.upsert(baseRecord({ value: "v2", version: 2 }));
    const rolled = store.rollback("m-1", "tenant-A");
    expect(rolled.value).toBe("v1");
    expect(store.get("m-1", "tenant-A").value).toBe("v1");
  });

  it(`[${contractName}] rollbackToVersion restores a specific historical version`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ value: "v1", version: 1 }));
    store.upsert(baseRecord({ value: "v2", version: 2 }));
    store.upsert(baseRecord({ value: "v3", version: 3 }));
    const rolled = store.rollbackToVersion("m-1", 1, "tenant-A");
    expect(rolled.value).toBe("v1");
    expect(store.get("m-1", "tenant-A").value).toBe("v1");
  });

  it(`[${contractName}] delete removes the record; subsequent get throws MemoryNotFoundError`, () => {
    const store = makeStore();
    store.upsert(baseRecord());
    store.delete("m-1", "tenant-A");
    let err: unknown;
    try { store.get("m-1", "tenant-A"); } catch (e) { err = e; }
    expect(errName(err)).toBe("MemoryNotFoundError");
  });

  it(`[${contractName}] delete of unknown memoryId is idempotent (no throw)`, () => {
    const store = makeStore();
    expect(() => store.delete("ghost", "tenant-A")).not.toThrow();
  });

  // ───── NEGATIVE: tenant isolation ─────

  it(`[${contractName}] NEGATIVE: get with wrong tenant throws MemoryAccessDeniedError`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ tenantId: "tenant-A" }));
    let err: unknown;
    try { store.get("m-1", "tenant-B"); } catch (e) { err = e; }
    expect(errName(err)).toBe("MemoryAccessDeniedError");
  });

  it(`[${contractName}] NEGATIVE: rollback with wrong tenant throws MemoryAccessDeniedError`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ value: "v1", version: 1 }));
    store.upsert(baseRecord({ value: "v2", version: 2 }));
    let err: unknown;
    try { store.rollback("m-1", "tenant-B"); } catch (e) { err = e; }
    expect(errName(err)).toBe("MemoryAccessDeniedError");
  });

  it(`[${contractName}] NEGATIVE: rollbackToVersion with wrong tenant throws MemoryAccessDeniedError`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ value: "v1", version: 1 }));
    store.upsert(baseRecord({ value: "v2", version: 2 }));
    let err: unknown;
    try { store.rollbackToVersion("m-1", 1, "tenant-B"); } catch (e) { err = e; }
    expect(errName(err)).toBe("MemoryAccessDeniedError");
  });

  it(`[${contractName}] NEGATIVE: delete with wrong tenant throws MemoryAccessDeniedError`, () => {
    const store = makeStore();
    store.upsert(baseRecord({ tenantId: "tenant-A" }));
    let err: unknown;
    try { store.delete("m-1", "tenant-B"); } catch (e) { err = e; }
    expect(errName(err)).toBe("MemoryAccessDeniedError");
  });
}

// ───────────────────────────── WorkflowStore contract ─────────────────────────────

export function runWorkflowStoreContract(
  contractName: string,
  makeStore: () => WorkflowStoreI,
): void {
  const baseState = (overrides: Partial<WorkflowState> = {}): WorkflowState => ({
    context: {
      workflowId: "wf-1",
      requestId: "req-1",
      tenantId: "tenant-A",
      userId: "user-1",
      traceId: "trace-1",
    },
    status: "created",
    userGoal: "ship feature X",
    steps: [],
    currentStepIndex: 0,
    createdAt: nowIso(),
    updatedAt: nowIso(),
    ...overrides,
  });

  it(`[${contractName}] BACKDOOR: save + get round-trip preserves workflowId + status`, () => {
    const store = makeStore();
    store.save(baseState({ status: "planning" }));
    const got = store.get("wf-1", "tenant-A");
    expect(got.context.workflowId).toBe("wf-1");
    expect(got.status).toBe("planning");
  });

  it(`[${contractName}] save twice grows historyDepth by 1`, () => {
    const store = makeStore();
    store.save(baseState({ status: "planning" }));
    expect(store.historyDepth("wf-1")).toBe(0);
    store.save(baseState({ status: "executing" }));
    expect(store.historyDepth("wf-1")).toBe(1);
  });

  it(`[${contractName}] rollback restores the previous saved state`, () => {
    const store = makeStore();
    store.save(baseState({ status: "planning" }));
    store.save(baseState({ status: "executing" }));
    const prev = store.rollback("wf-1", "tenant-A");
    expect(prev.status).toBe("planning");
    expect(store.get("wf-1", "tenant-A").status).toBe("planning");
  });

  it(`[${contractName}] get of unknown workflow throws WorkflowNotFoundError`, () => {
    const store = makeStore();
    let err: unknown;
    try { store.get("ghost", "tenant-A"); } catch (e) { err = e; }
    expect(errName(err)).toBe("WorkflowNotFoundError");
  });

  // ───── NEGATIVE: tenant isolation ─────

  it(`[${contractName}] NEGATIVE: get with wrong tenant throws WorkflowAccessDeniedError`, () => {
    const store = makeStore();
    store.save(baseState({ status: "planning" }));
    let err: unknown;
    try { store.get("wf-1", "tenant-B"); } catch (e) { err = e; }
    expect(errName(err)).toBe("WorkflowAccessDeniedError");
  });

  it(`[${contractName}] NEGATIVE: rollback with wrong tenant throws WorkflowAccessDeniedError`, () => {
    const store = makeStore();
    store.save(baseState({ status: "planning" }));
    store.save(baseState({ status: "executing" }));
    let err: unknown;
    try { store.rollback("wf-1", "tenant-B"); } catch (e) { err = e; }
    expect(errName(err)).toBe("WorkflowAccessDeniedError");
  });

  it(`[${contractName}] NEGATIVE: save with same workflowId but different tenantId throws WorkflowAccessDeniedError`, () => {
    const store = makeStore();
    store.save(baseState({ status: "planning" }));
    let err: unknown;
    try {
      store.save(baseState({
        status: "executing",
        context: {
          workflowId: "wf-1",
          requestId: "req-2",
          tenantId: "tenant-B",  // tenant flip on same workflowId — must reject
          userId: "user-2",
          traceId: "trace-2",
        },
      }));
    } catch (e) { err = e; }
    expect(errName(err)).toBe("WorkflowAccessDeniedError");
  });
}

// ───────────────────────────── MemoryAuditLog contract ─────────────────────────────

export function runMemoryAuditLogContract(
  contractName: string,
  makeLog: () => MemoryAuditLogI,
): void {
  const baseRecord = (overrides: Partial<AuditRecord> = {}): AuditRecord => ({
    auditId: "a-1",
    memoryId: "m-1",
    action: "create",
    actorUserId: "user-1",
    tenantId: "tenant-A",
    newValue: "v1",
    reason: "test",
    timestamp: nowIso(),
    ...overrides,
  });

  it(`[${contractName}] BACKDOOR: append + listByMemory returns the appended record`, () => {
    const log = makeLog();
    log.append(baseRecord());
    const rows = log.listByMemory("m-1");
    expect(rows).toHaveLength(1);
    expect(rows[0].auditId).toBe("a-1");
  });

  it(`[${contractName}] listByMemory returns empty array for unknown memoryId`, () => {
    const log = makeLog();
    expect(log.listByMemory("ghost")).toEqual([]);
  });

  it(`[${contractName}] append preserves chronological insert order`, () => {
    const log = makeLog();
    log.append(baseRecord({ auditId: "a-1", reason: "first" }));
    log.append(baseRecord({ auditId: "a-2", reason: "second" }));
    log.append(baseRecord({ auditId: "a-3", reason: "third" }));
    const rows = log.listByMemory("m-1");
    expect(rows.map((r) => r.auditId)).toEqual(["a-1", "a-2", "a-3"]);
  });

  // ───── NEGATIVE ─────

  it(`[${contractName}] NEGATIVE: listByMemory filters out records for OTHER memoryIds`, () => {
    const log = makeLog();
    log.append(baseRecord({ auditId: "a-1", memoryId: "m-1" }));
    log.append(baseRecord({ auditId: "a-2", memoryId: "m-2" }));
    log.append(baseRecord({ auditId: "a-3", memoryId: "m-1" }));
    const rows = log.listByMemory("m-1");
    expect(rows.map((r) => r.auditId).sort()).toEqual(["a-1", "a-3"]);
    expect(rows.every((r) => r.memoryId === "m-1")).toBe(true);
  });

  it(`[${contractName}] NEGATIVE: mutating the returned array does not affect stored records`, () => {
    const log = makeLog();
    log.append(baseRecord());
    const rows = log.listByMemory("m-1");
    rows[0].reason = "MUTATED";
    rows.push(baseRecord({ auditId: "INJECTED" }));
    const second = log.listByMemory("m-1");
    expect(second).toHaveLength(1);
    expect(second[0].reason).toBe("test");
  });
}

// ───────────────────────────── SessionPersistenceStore contract ─────────────────────────────

export function runSessionPersistenceStoreContract(
  contractName: string,
  makeStore: () => SessionPersistenceStoreI,
): void {
  const baseSession = (overrides: Partial<SessionState> = {}): SessionState => ({
    sessionId: "tenant-A:web:user-1",
    userId: "user-1",
    tenantId: "tenant-A",
    channel: "web",
    history: [],
    createdAt: nowIso(),
    updatedAt: nowIso(),
    ...overrides,
  });

  it(`[${contractName}] BACKDOOR: set + get round-trip returns the session`, () => {
    const store = makeStore();
    store.set("s-1", baseSession({ sessionId: "s-1" }));
    expect(store.get("s-1")?.sessionId).toBe("s-1");
  });

  it(`[${contractName}] delete removes the session; subsequent get returns undefined`, () => {
    const store = makeStore();
    store.set("s-1", baseSession({ sessionId: "s-1" }));
    store.delete("s-1");
    expect(store.get("s-1")).toBeUndefined();
  });

  it(`[${contractName}] entries iterates all stored sessions`, () => {
    const store = makeStore();
    store.set("s-1", baseSession({ sessionId: "s-1" }));
    store.set("s-2", baseSession({ sessionId: "s-2" }));
    store.set("s-3", baseSession({ sessionId: "s-3" }));
    const keys = Array.from(store.entries()).map(([k]) => k).sort();
    expect(keys).toEqual(["s-1", "s-2", "s-3"]);
  });

  it(`[${contractName}] oldestKey returns the first-inserted key (insertion-order LRU contract)`, () => {
    const store = makeStore();
    store.set("s-first", baseSession({ sessionId: "s-first" }));
    store.set("s-second", baseSession({ sessionId: "s-second" }));
    store.set("s-third", baseSession({ sessionId: "s-third" }));
    expect(store.oldestKey()).toBe("s-first");
  });

  it(`[${contractName}] size reflects the number of stored sessions`, () => {
    const store = makeStore();
    expect(store.size()).toBe(0);
    store.set("s-1", baseSession({ sessionId: "s-1" }));
    store.set("s-2", baseSession({ sessionId: "s-2" }));
    expect(store.size()).toBe(2);
    store.delete("s-1");
    expect(store.size()).toBe(1);
  });

  // ───── NEGATIVE ─────

  it(`[${contractName}] NEGATIVE: get of unknown sessionId returns undefined (NOT throw)`, () => {
    const store = makeStore();
    expect(store.get("ghost")).toBeUndefined();
  });

  it(`[${contractName}] NEGATIVE: delete of unknown sessionId is idempotent (no throw)`, () => {
    const store = makeStore();
    expect(() => store.delete("ghost")).not.toThrow();
  });

  it(`[${contractName}] NEGATIVE: oldestKey on empty store returns undefined`, () => {
    const store = makeStore();
    expect(store.oldestKey()).toBeUndefined();
  });
}
