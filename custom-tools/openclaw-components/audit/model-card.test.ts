// Negative drills for Iter 111 (2026-05-18): ModelCardRegistry +
// ModelCard schema. Locks the §48.3 minimum disclosure contract
// for every model that serves production traffic.

import { describe, it, expect } from "vitest";
import {
  ModelCard,
  ModelCardRegistry,
  ModelCardMissingError,
  ModelCardInvalidError,
} from "./model-card";

const VALID_CARD = (overrides: Partial<ModelCard> = {}): ModelCard => ({
  modelId: "gpt-4o:2024-08",
  version: "2024-08-13",
  intendedUse: "General-purpose chat + tool dispatch for tier-1 tenants.",
  owner: { team: "platform-llm", contactEmail: "platform-llm@example.com" },
  lastReviewedAt: new Date().toISOString(),
  ...overrides,
});

describe("Iter 111 — ModelCardRegistry (P1)", () => {
  it("BACKDOOR: register + get round-trips a valid card", () => {
    const r = new ModelCardRegistry();
    r.register(VALID_CARD());
    const c = r.get("gpt-4o:2024-08");
    expect(c).toBeDefined();
    expect(c!.intendedUse).toContain("General-purpose");
  });

  it("BACKDOOR: require() throws ModelCardMissingError on absent model", () => {
    const r = new ModelCardRegistry();
    expect(() => r.require("never-registered")).toThrow(ModelCardMissingError);
  });

  it("BACKDOOR: require() returns the card when present", () => {
    const r = new ModelCardRegistry();
    r.register(VALID_CARD());
    expect(() => r.require("gpt-4o:2024-08")).not.toThrow();
    const c = r.require("gpt-4o:2024-08");
    expect(c.modelId).toBe("gpt-4o:2024-08");
  });

  it("BACKDOOR: register rejects empty modelId", () => {
    const r = new ModelCardRegistry();
    expect(() => r.register(VALID_CARD({ modelId: "" })))
      .toThrow(ModelCardInvalidError);
  });

  it("BACKDOOR: register rejects empty version", () => {
    const r = new ModelCardRegistry();
    expect(() => r.register(VALID_CARD({ version: "" })))
      .toThrow(/version required/);
  });

  it("BACKDOOR: register rejects empty intendedUse", () => {
    const r = new ModelCardRegistry();
    expect(() => r.register(VALID_CARD({ intendedUse: "" })))
      .toThrow(/intendedUse required/);
  });

  it("BACKDOOR: register rejects missing owner.team", () => {
    const r = new ModelCardRegistry();
    expect(() => r.register(VALID_CARD({
      owner: { team: "" },
    }))).toThrow(/owner\.team required/);
  });

  it("BACKDOOR: register rejects malformed lastReviewedAt", () => {
    const r = new ModelCardRegistry();
    expect(() => r.register(VALID_CARD({ lastReviewedAt: "not-a-date" })))
      .toThrow(/ISO-8601/);
  });

  it("optional fields ride through unchanged (forensic completeness)", () => {
    const r = new ModelCardRegistry();
    const card: ModelCard = VALID_CARD({
      outOfScopeUses: ["medical diagnosis", "legal advice"],
      trainingDataSummary: "Web crawl + curated tech corpus.",
      trainingDataAsOf: "2024-04-30T00:00:00Z",
      performance: { faithfulness: 0.92, answerRelevance: 0.88 },
      fairness: { disparateImpact: 0.86, equalOpportunityGapPercent: 3.1 },
      explainability: { method: "shap", globalShapUrl: "https://x/shap.html" },
      history: [{ version: "2024-05", releasedAt: "2024-05-01T00:00:00Z" }],
      limitations: ["Cuts off at 128k tokens", "May hallucinate post-2024 facts"],
    });
    r.register(card);
    const got = r.require("gpt-4o:2024-08")!;
    expect(got.outOfScopeUses).toEqual(["medical diagnosis", "legal advice"]);
    expect(got.performance?.faithfulness).toBe(0.92);
    expect(got.fairness?.disparateImpact).toBe(0.86);
    expect(got.explainability?.method).toBe("shap");
    expect(got.history?.length).toBe(1);
    expect(got.limitations?.length).toBe(2);
  });

  it("list() returns all registered modelIds sorted", () => {
    const r = new ModelCardRegistry();
    r.register(VALID_CARD({ modelId: "model-b" }));
    r.register(VALID_CARD({ modelId: "model-a" }));
    r.register(VALID_CARD({ modelId: "model-c" }));
    expect(r.list()).toEqual(["model-a", "model-b", "model-c"]);
  });

  it("BACKDOOR: staleReviews flags cards past the maxAgeDays cutoff", () => {
    const r = new ModelCardRegistry();
    const oldDate = new Date(Date.now() - 200 * 24 * 60 * 60 * 1000).toISOString();
    const freshDate = new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString();
    r.register(VALID_CARD({ modelId: "old-1", lastReviewedAt: oldDate }));
    r.register(VALID_CARD({ modelId: "old-2", lastReviewedAt: oldDate }));
    r.register(VALID_CARD({ modelId: "fresh", lastReviewedAt: freshDate }));

    // Quarterly = 90 days; both old-* should be flagged.
    expect(r.staleReviews(90)).toEqual(["old-1", "old-2"]);
    // 365-day window: nothing stale.
    expect(r.staleReviews(365)).toEqual([]);
  });

  it("staleReviews rejects negative maxAgeDays", () => {
    const r = new ModelCardRegistry();
    expect(() => r.staleReviews(-1)).toThrow(/maxAgeDays/);
  });

  it("staleReviews accepts 0 (everything stale)", () => {
    const r = new ModelCardRegistry();
    r.register(VALID_CARD());
    // Wait 1 ms then check
    expect(r.staleReviews(0, new Date(Date.now() + 1))).toContain("gpt-4o:2024-08");
  });

  it("re-register with same modelId overwrites (intentional — used during release rollback)", () => {
    const r = new ModelCardRegistry();
    r.register(VALID_CARD({ version: "v1" }));
    r.register(VALID_CARD({ version: "v2" }));
    expect(r.require("gpt-4o:2024-08").version).toBe("v2");
  });

  it("ModelCardMissingError + ModelCardInvalidError name fields locked", () => {
    expect(new ModelCardMissingError("x").name).toBe("ModelCardMissingError");
    expect(new ModelCardInvalidError("x", "reason").name).toBe("ModelCardInvalidError");
  });

  it("ModelCardMissingError + ModelCardInvalidError instanceof Error", () => {
    expect(new ModelCardMissingError("x")).toBeInstanceOf(Error);
    expect(new ModelCardInvalidError("x", "r")).toBeInstanceOf(Error);
  });
});
