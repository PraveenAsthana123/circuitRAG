// Negative drills for Iter 83 (2026-05-18): RoutingPolicy edge cases.
// Existing tests cover integration via the router. This drill exercises
// estimateCost + maxEstimatedCostForTenant + selectModel directly.

import { describe, it, expect } from "vitest";
import { RoutingPolicy } from "./routing-policy";
import { LLMRequest, ModelConfig } from "./types";

const M = (id: string, costPer1k: number, priority = 1): ModelConfig => ({
  modelId: id, provider: "ollama", supportedTasks: ["code"],
  costPer1kTokensUsd: costPer1k, maxContextTokens: 8192,
  priority, enabled: true,
});

const REQ = (overrides: Partial<LLMRequest> = {}): LLMRequest => ({
  requestId: "r", tenantId: "t-1", userId: "u-1",
  taskType: "code", prompt: "x", maxTokens: 1000,
  traceId: "tr", ...overrides,
});

describe("Iter 83 — RoutingPolicy edge cases (P2)", () => {
  it("BACKDOOR: constructor rejects negative default cost cap", () => {
    expect(() => new RoutingPolicy({ defaultMaxEstimatedCostUsd: -0.01 }))
      .toThrow(/>= 0/);
  });

  it("BACKDOOR: constructor rejects negative per-tenant cost cap", () => {
    expect(() => new RoutingPolicy({
      tenantMaxEstimatedCostUsd: { "t-1": -0.01 },
    })).toThrow(/>= 0/);
  });

  it("default cap accepts 0 (free-tier-only contract)", () => {
    const p = new RoutingPolicy({ defaultMaxEstimatedCostUsd: 0 });
    expect(p.maxEstimatedCostForTenant("any")).toBe(0);
  });

  it("estimateCost is linear in maxTokens / 1000", () => {
    const p = new RoutingPolicy();
    expect(p.estimateCost(REQ({ maxTokens: 1000 }), M("m", 0.5))).toBe(0.5);
    expect(p.estimateCost(REQ({ maxTokens: 2000 }), M("m", 0.5))).toBe(1.0);
    expect(p.estimateCost(REQ({ maxTokens: 500 }), M("m", 0.5))).toBe(0.25);
  });

  it("estimateCost of 0-cost model is always 0", () => {
    const p = new RoutingPolicy();
    expect(p.estimateCost(REQ({ maxTokens: 999_999 }), M("free", 0))).toBe(0);
  });

  it("BACKDOOR: maxEstimatedCostForTenant returns tenant-specific value when configured", () => {
    const p = new RoutingPolicy({
      defaultMaxEstimatedCostUsd: 1.0,
      tenantMaxEstimatedCostUsd: { "vip": 100.0, "free": 0 },
    });
    expect(p.maxEstimatedCostForTenant("vip")).toBe(100);
    expect(p.maxEstimatedCostForTenant("free")).toBe(0);
    expect(p.maxEstimatedCostForTenant("other")).toBe(1.0);  // default
  });

  it("BACKDOOR: selectModel returns the FIRST affordable candidate (priority order preserved)", () => {
    const p = new RoutingPolicy({ defaultMaxEstimatedCostUsd: 5.0 });
    const candidates = [
      M("expensive", 10, 1),  // 10 USD/k * 1k = 10 USD — TOO MUCH
      M("cheap", 0.1, 2),
      M("free", 0, 3),
    ];
    const selected = p.selectModel(REQ(), candidates);
    expect(selected.modelId).toBe("cheap");  // first affordable
  });

  it("BACKDOOR: selectModel throws when NO candidate is affordable", () => {
    const p = new RoutingPolicy({ defaultMaxEstimatedCostUsd: 0.001 });
    const candidates = [M("a", 1), M("b", 2), M("c", 5)];
    expect(() => p.selectModel(REQ(), candidates))
      .toThrow(/No affordable/);
  });

  it("selectModel: empty candidate list throws", () => {
    const p = new RoutingPolicy();
    expect(() => p.selectModel(REQ(), [])).toThrow(/No affordable/);
  });

  it("BOUNDARY: cost EXACTLY at cap is accepted (inclusive)", () => {
    // maxTokens=1000, costPer1k=1 → cost=1.0. Cap=1.0 → accept.
    const p = new RoutingPolicy({ defaultMaxEstimatedCostUsd: 1.0 });
    const candidates = [M("at-cap", 1)];
    expect(() => p.selectModel(REQ({ maxTokens: 1000 }), candidates))
      .not.toThrow();
  });

  it("BOUNDARY: cost JUST OVER cap is rejected", () => {
    const p = new RoutingPolicy({ defaultMaxEstimatedCostUsd: 0.99 });
    const candidates = [M("over", 1)];  // 1.0 > 0.99
    expect(() => p.selectModel(REQ({ maxTokens: 1000 }), candidates))
      .toThrow(/No affordable/);
  });

  it("zero-cap tenant cannot afford ANY paid model (free-tier-only contract)", () => {
    const p = new RoutingPolicy({
      tenantMaxEstimatedCostUsd: { "free-tier": 0 },
    });
    const candidates = [M("free", 0), M("paid", 0.001)];
    const req = REQ({ tenantId: "free-tier" });
    const selected = p.selectModel(req, candidates);
    expect(selected.modelId).toBe("free");  // only free passes
  });

  it("priority order is HONORED before cost filter (regression)", () => {
    // Priority 1 model (preferred) is affordable. Don't fall back
    // to lower-priority just because both are affordable.
    const p = new RoutingPolicy({ defaultMaxEstimatedCostUsd: 5.0 });
    const candidates = [
      M("preferred", 0.1, 1),  // priority 1
      M("fallback", 0.1, 2),    // priority 2
    ];
    // Note: candidates here are pre-sorted by router's ModelRegistry;
    // the policy preserves input order. The drill locks that the
    // policy is NOT re-sorting.
    const selected = p.selectModel(REQ(), candidates);
    expect(selected.modelId).toBe("preferred");
  });
});
