import { describe, it, expect } from "vitest";
import { MemoryGovernanceService } from "./memory-governance-service";
import { MemoryStore } from "./memory-store";
import { MemoryAuditLog } from "./memory-audit-log";
import { PIIMasker } from "./pii-masker";
import { RetentionPolicy } from "./retention-policy";

describe("MemoryGovernanceService", () => {
  it("masks PII and stores audited memory", () => {
    const service = new MemoryGovernanceService(
      new MemoryStore(),
      new MemoryAuditLog(),
      new PIIMasker(),
      new RetentionPolicy()
    );

    const saved = service.save({
      tenantId: "tenant-1",
      userId: "user-1",
      actorUserId: "user-1",
      key: "preferred_stack",
      value: "User prefers TypeScript. Email: test@example.com",
      reason: "User preference for future coding examples",
      retentionDays: 365,
    });

    expect(saved.value).toContain("[EMAIL]");
    expect(saved.version).toBe(1);
  });
});
