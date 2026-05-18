// Negative drills for Iter 79 (2026-05-17): CostLedger edge cases.
// Existing tests cover the happy path via router integration; this
// drill exercises the ledger directly at boundaries.

import { describe, it, expect } from "vitest";
import { CostLedger, CostLedgerEntry } from "./cost-ledger";

const E = (overrides: Partial<CostLedgerEntry> = {}): CostLedgerEntry => ({
  requestId: "r", tenantId: "t-1", userId: "u-1",
  modelId: "m", provider: "ollama", taskType: "code",
  estimatedCostUsd: 0.5,
  timestamp: new Date().toISOString(),
  ...overrides,
});

describe("Iter 79 — CostLedger bounds (P2)", () => {
  it("BACKDOOR: negative cost rejected (defense against bad provider response)", () => {
    const l = new CostLedger();
    expect(() => l.record(E({ estimatedCostUsd: -0.01 }))).toThrow(/>= 0/);
  });

  it("zero-cost record is accepted (free local model path)", () => {
    const l = new CostLedger();
    expect(() => l.record(E({ estimatedCostUsd: 0 }))).not.toThrow();
    expect(l.getTenantSpend("t-1")).toBe(0);
  });

  it("BACKDOOR: tenant spend isolated — A's record does not leak to B", () => {
    const l = new CostLedger();
    l.record(E({ tenantId: "t-A", estimatedCostUsd: 1 }));
    expect(l.getTenantSpend("t-A")).toBe(1);
    expect(l.getTenantSpend("t-B")).toBe(0);
  });

  it("BACKDOOR: user spend isolated WITHIN same tenant", () => {
    const l = new CostLedger();
    l.record(E({ userId: "u-1", estimatedCostUsd: 0.3 }));
    l.record(E({ userId: "u-2", estimatedCostUsd: 0.7 }));
    expect(l.getUserSpend("t-1", "u-1")).toBe(0.3);
    expect(l.getUserSpend("t-1", "u-2")).toBe(0.7);
    expect(l.getTenantSpend("t-1")).toBeCloseTo(1.0);
  });

  it("same user+tenant: spend accumulates across records", () => {
    const l = new CostLedger();
    l.record(E({ estimatedCostUsd: 0.1 }));
    l.record(E({ estimatedCostUsd: 0.2 }));
    l.record(E({ estimatedCostUsd: 0.3 }));
    expect(l.getUserSpend("t-1", "u-1")).toBeCloseTo(0.6);
    expect(l.getTenantSpend("t-1")).toBeCloseTo(0.6);
  });

  it("listEntries returns DEFENSIVE COPIES (mutation does not affect internal state)", () => {
    const l = new CostLedger();
    l.record(E({ estimatedCostUsd: 0.5 }));
    const copy = l.listEntries();
    copy[0].estimatedCostUsd = 9999;
    // Internal state unchanged.
    expect(l.getTenantSpend("t-1")).toBe(0.5);
    expect(l.listEntries()[0].estimatedCostUsd).toBe(0.5);
  });

  it("getTenantSpend/getUserSpend return 0 for never-seen ids (no crash)", () => {
    const l = new CostLedger();
    expect(l.getTenantSpend("never-seen")).toBe(0);
    expect(l.getUserSpend("t", "never-seen")).toBe(0);
  });

  it("cross-tenant user collision: same userId in different tenants is INDEPENDENT", () => {
    // User "u-1" in tenant-A is a completely different account from
    // user "u-1" in tenant-B. The user-key implementation must include
    // tenantId in the key.
    const l = new CostLedger();
    l.record(E({ tenantId: "t-A", userId: "u-1", estimatedCostUsd: 1 }));
    l.record(E({ tenantId: "t-B", userId: "u-1", estimatedCostUsd: 5 }));
    expect(l.getUserSpend("t-A", "u-1")).toBe(1);
    expect(l.getUserSpend("t-B", "u-1")).toBe(5);
  });

  it("entries are RECORDED as defensive copies (caller mutation does not leak in)", () => {
    const l = new CostLedger();
    const entry = E({ estimatedCostUsd: 0.5 });
    l.record(entry);
    entry.estimatedCostUsd = 999;  // caller mutates AFTER record
    expect(l.getTenantSpend("t-1")).toBe(0.5);  // ledger unaffected
  });
});
