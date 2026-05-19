// Iter 120 (2026-05-19): runs the storage-contracts.ts behavioral
// corpus against every in-memory adapter. The same corpus will be
// invoked from a future contracts/postgres-contracts.test.ts +
// contracts/redis-contracts.test.ts with the production adapter
// factories — proving drop-in compatibility without rewriting
// the assertions.
//
// Per CLAUDE.md §43 (drill) + §57.7 (drilled invariants prove
// contract) + §59.1 MDD (the contract IS the model; the adapter
// is one derivation).

import { describe } from "vitest";
import {
  runMemoryStoreContract,
  runWorkflowStoreContract,
  runMemoryAuditLogContract,
  runSessionPersistenceStoreContract,
} from "./storage-contracts";

import { MemoryStore } from "../04-memory-governance/memory-store";
import { MemoryAuditLog } from "../04-memory-governance/memory-audit-log";
import { WorkflowStateStore } from "../10-agent-workflow/workflow-state-store";
import { InMemorySessionStore } from "../01-gateway/session-manager";

describe("Iter 120 — in-memory storage adapters satisfy behavioral contracts", () => {
  describe("MemoryStore", () => {
    runMemoryStoreContract("in-memory MemoryStore", () => new MemoryStore());
  });

  describe("WorkflowStateStore", () => {
    runWorkflowStoreContract("in-memory WorkflowStateStore", () => new WorkflowStateStore());
  });

  describe("MemoryAuditLog", () => {
    runMemoryAuditLogContract("in-memory MemoryAuditLog", () => new MemoryAuditLog());
  });

  describe("InMemorySessionStore", () => {
    runSessionPersistenceStoreContract(
      "InMemorySessionStore",
      () => new InMemorySessionStore(),
    );
  });
});
