export type MemoryScope = "session" | "user" | "tenant";
export type MemoryAction = "create" | "read" | "update" | "delete" | "rollback";

export interface MemoryRecord {
  memoryId: string;
  tenantId: string;
  userId: string;
  scope: MemoryScope;
  key: string;
  value: string;
  version: number;
  createdAt: string;
  updatedAt: string;
  expiresAt?: string;
}

export interface AuditRecord {
  auditId: string;
  memoryId: string;
  action: MemoryAction;
  actorUserId: string;
  tenantId: string;
  previousValue?: string;
  newValue?: string;
  reason: string;
  traceId?: string;
  timestamp: string;
}
