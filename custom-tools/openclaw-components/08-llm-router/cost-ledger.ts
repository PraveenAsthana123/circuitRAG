export interface CostLedgerEntry {
  requestId: string;
  tenantId: string;
  userId: string;
  modelId: string;
  provider: string;
  taskType: string;
  estimatedCostUsd: number;
  timestamp: string;
}

export class CostLedger {
  private readonly entries: CostLedgerEntry[] = [];
  private readonly tenantTotals = new Map<string, number>();
  private readonly userTotals = new Map<string, number>();

  record(entry: CostLedgerEntry): void {
    if (entry.estimatedCostUsd < 0) {
      throw new Error("estimatedCostUsd must be >= 0");
    }

    this.entries.push({ ...entry });
    this.tenantTotals.set(
      entry.tenantId,
      this.getTenantSpend(entry.tenantId) + entry.estimatedCostUsd,
    );
    const userKey = this.userKey(entry.tenantId, entry.userId);
    this.userTotals.set(
      userKey,
      this.getUserSpend(entry.tenantId, entry.userId) + entry.estimatedCostUsd,
    );
  }

  getTenantSpend(tenantId: string): number {
    return this.tenantTotals.get(tenantId) ?? 0;
  }

  getUserSpend(tenantId: string, userId: string): number {
    return this.userTotals.get(this.userKey(tenantId, userId)) ?? 0;
  }

  listEntries(): CostLedgerEntry[] {
    return this.entries.map((entry) => ({ ...entry }));
  }

  private userKey(tenantId: string, userId: string): string {
    return `${tenantId}:${userId}`;
  }
}
