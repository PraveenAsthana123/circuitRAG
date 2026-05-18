// Negative drills for M3.2 (2026-05-18): storage interface contracts.
// Locks the seam where Phase 2.2 Postgres/Redis adapters will plug
// in. Each existing in-memory impl is asserted to be compatible
// with its interface — so a refactor that drifts the shape fails
// loudly at PR time rather than silently breaking future adapters.

import { describe, it, expect } from "vitest";
import type {
  WorkflowStoreI,
  MemoryStoreI,
  MemoryAuditLogI,
  SessionStoreI,
  StorageBundle,
} from "./interfaces";
import { WorkflowStateStore } from "./10-agent-workflow/workflow-state-store";
import { MemoryStore } from "./04-memory-governance/memory-store";
import { MemoryAuditLog } from "./04-memory-governance/memory-audit-log";
import { SessionManager } from "./01-gateway/session-manager";

describe("M3.2 — storage interface contract compatibility (P1)", () => {
  it("BACKDOOR: WorkflowStateStore satisfies WorkflowStoreI", () => {
    // TS compile-time check via the assignment.
    const store: WorkflowStoreI = new WorkflowStateStore();
    // Runtime check: every required method exists + is callable.
    expect(typeof store.save).toBe("function");
    expect(typeof store.get).toBe("function");
    expect(typeof store.rollback).toBe("function");
    expect(typeof store.historyDepth).toBe("function");
  });

  it("BACKDOOR: MemoryStore satisfies MemoryStoreI", () => {
    const store: MemoryStoreI = new MemoryStore();
    expect(typeof store.upsert).toBe("function");
    expect(typeof store.get).toBe("function");
    expect(typeof store.findByKey).toBe("function");
    expect(typeof store.rollback).toBe("function");
    expect(typeof store.rollbackToVersion).toBe("function");
    expect(typeof store.delete).toBe("function");
  });

  it("BACKDOOR: MemoryAuditLog satisfies MemoryAuditLogI", () => {
    const log: MemoryAuditLogI = new MemoryAuditLog();
    expect(typeof log.append).toBe("function");
    expect(typeof log.listByMemory).toBe("function");
  });

  it("BACKDOOR: SessionManager satisfies SessionStoreI", () => {
    const session: SessionStoreI = new SessionManager();
    expect(typeof session.getOrCreateSession).toBe("function");
    expect(typeof session.size).toBe("function");
  });

  it("BACKDOOR: in-memory StorageBundle composes (local-mode wiring regression)", () => {
    const bundle: StorageBundle = {
      workflow: new WorkflowStateStore(),
      memory: new MemoryStore(),
      audit: new MemoryAuditLog(),
      session: new SessionManager(),
      mode: "local",
    };
    expect(bundle.mode).toBe("local");
    expect(bundle.workflow).toBeDefined();
    expect(bundle.memory).toBeDefined();
    expect(bundle.audit).toBeDefined();
    expect(bundle.session).toBeDefined();
  });

  it("test-mode StorageBundle (in-memory adapters) accepted", () => {
    const bundle: StorageBundle = {
      workflow: new WorkflowStateStore(),
      memory: new MemoryStore(),
      audit: new MemoryAuditLog(),
      session: new SessionManager(),
      mode: "test",
    };
    expect(bundle.mode).toBe("test");
  });

  it("DeploymentMode type accepts the three documented values only (regression)", () => {
    // The type is a string-literal union; assigning each must compile.
    const local: StorageBundle["mode"] = "local";
    const test: StorageBundle["mode"] = "test";
    const production: StorageBundle["mode"] = "production";
    expect([local, test, production]).toEqual(["local", "test", "production"]);
  });

  it("interface change to WorkflowStoreI would fail typecheck on existing store (regression)", () => {
    // This drill asserts the SHAPE is locked. If a future refactor
    // removed e.g. WorkflowStateStore.historyDepth(), the line
    // `const store: WorkflowStoreI = new WorkflowStateStore()` in
    // the first drill above would fail tsc. This test asserts at
    // runtime that the methods exist.
    const store = new WorkflowStateStore();
    expect("save" in store).toBe(true);
    expect("get" in store).toBe(true);
    expect("rollback" in store).toBe(true);
    expect("historyDepth" in store).toBe(true);
  });

  it("end-to-end: each in-memory adapter operates through its interface contract", () => {
    // Functional regression: use each adapter through the interface
    // type so a refactor that breaks the contract surfaces here.
    const memory: MemoryStoreI = new MemoryStore();
    const record = memory.upsert({
      memoryId: "m-1", tenantId: "t-1", userId: "u-1",
      scope: "user", key: "k", value: "v", version: 1,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    expect(record.memoryId).toBe("m-1");
    expect(memory.findByKey("t-1", "u-1", "k")?.value).toBe("v");

    const audit: MemoryAuditLogI = new MemoryAuditLog();
    audit.append({
      auditId: "a-1", memoryId: "m-1", action: "create",
      actorUserId: "u-1", tenantId: "t-1",
      newValue: "v", reason: "test",
      timestamp: new Date().toISOString(),
    });
    expect(audit.listByMemory("m-1").length).toBe(1);
  });
});
