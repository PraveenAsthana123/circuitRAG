// Iter M3.2 (2026-05-18): cross-component storage interfaces.
//
// Phase 2.2 of the production-readiness plan: define the seam
// where Postgres / Redis / Kafka / S3 adapters drop in. Existing
// in-memory implementations satisfy these interfaces unchanged;
// production adapters implement the same shape. A future
// composition root (root config + DI wiring) picks the right
// adapter per `mode: "local" | "test" | "production"`.
//
// Per CLAUDE.md §47 (boundary discipline) + §53 (enterprise AI
// maturity stack item 35: durable state).
//
// These are MARKER interfaces — they describe the public-API
// surface of existing classes. The classes themselves don't yet
// `implements` the interface (they predate it); a contract drill
// (storage-interface-contracts.test.ts) asserts shape compatibility
// at type-check time + runtime so a refactor that drifts the
// in-memory shape fails loudly.

import type { WorkflowState } from "./10-agent-workflow/types";
import type { MemoryRecord, AuditRecord } from "./04-memory-governance/types";
import type { SessionState, UserMessage } from "./01-gateway/types";

/**
 * WorkflowStoreI — what production WorkflowStateStore must offer.
 * Existing WorkflowStateStore (10-agent-workflow/workflow-state-store.ts)
 * already implements this shape; a future PostgresWorkflowStore
 * binds to the same interface.
 */
export interface WorkflowStoreI {
  save(state: WorkflowState): void;
  get(workflowId: string, callerTenantId: string): WorkflowState;
  rollback(workflowId: string, callerTenantId: string): WorkflowState;
  historyDepth(workflowId: string): number;
}

/**
 * MemoryStoreI — what production MemoryStore must offer.
 * Existing MemoryStore (04-memory-governance/memory-store.ts)
 * already implements this shape.
 */
export interface MemoryStoreI {
  upsert(record: MemoryRecord): MemoryRecord;
  get(memoryId: string, callerTenantId: string): MemoryRecord;
  findByKey(tenantId: string, userId: string, key: string): MemoryRecord | undefined;
  rollback(memoryId: string, callerTenantId: string): MemoryRecord;
  rollbackToVersion(memoryId: string, targetVersion: number, callerTenantId: string): MemoryRecord;
  delete(memoryId: string, callerTenantId: string): void;
}

/**
 * MemoryAuditLogI — what production audit-log adapter must offer.
 * In-memory MemoryAuditLog (04-memory-governance/memory-audit-log.ts)
 * implements this; future PostgresAuditLog appends to an append-only
 * table per §38 schema.
 */
export interface MemoryAuditLogI {
  append(record: AuditRecord): void;
  listByMemory(memoryId: string): AuditRecord[];
}

/**
 * SessionStoreI — what production SessionManager must offer.
 * Existing SessionManager (01-gateway/session-manager.ts) implements
 * this; future RedisSessionStore binds to the same interface for
 * cross-replica session continuity.
 */
export interface SessionStoreI {
  getOrCreateSession(message: UserMessage): SessionState;
  size(): number;
}

/**
 * Iter 105 (2026-05-18): SessionPersistenceStoreI — the lower-level
 * persistence adapter that SessionManager delegates to (iter 104).
 * Distinct from SessionStoreI which is the SessionManager's PUBLIC
 * facade; this interface is the SEAM where Redis / Postgres adapters
 * plug in WITHOUT changing SessionManager itself.
 *
 * The two interfaces compose:
 *   Gateway → SessionManager (SessionStoreI) → SessionPersistenceStore (this)
 *
 * In-memory adapter: InMemorySessionStore in 01-gateway/session-manager.ts.
 * Production adapter: a future RedisSessionPersistenceStore implementing
 * the same shape, swapped in via the SessionManager constructor's 3rd arg.
 */
export interface SessionPersistenceStoreI {
  get(sessionId: string): SessionState | undefined;
  set(sessionId: string, session: SessionState): void;
  delete(sessionId: string): void;
  entries(): Iterable<[string, SessionState]>;
  oldestKey(): string | undefined;
  size(): number;
}

/**
 * Mode marker — exported here so each adapter's startup code can
 * branch on it. `local` and `test` accept in-memory impls;
 * `production` requires real adapters (enforced by composite
 * production-mode guards per M1.2).
 */
export type DeploymentMode = "local" | "test" | "production";

/**
 * StorageBundle — convenience shape for the composition root.
 * A future ProductionStorageBundle would resolve every field to
 * a Postgres/Redis adapter; in-memory bundle works in dev.
 *
 * Iter 105: `sessionPersistence` added — the lower-level adapter
 * the SessionManager facade delegates to. Local mode wires both
 * to in-memory implementations; production mode wires `session`
 * to the SessionManager (which in turn binds to the
 * Redis/Postgres `sessionPersistence`).
 */
export interface StorageBundle {
  workflow: WorkflowStoreI;
  memory: MemoryStoreI;
  audit: MemoryAuditLogI;
  session: SessionStoreI;
  sessionPersistence: SessionPersistenceStoreI;
  mode: DeploymentMode;
}
