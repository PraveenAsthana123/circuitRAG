// Iter 133 (2026-05-20): drill the failure decision matrix.
//
// The most important invariants are the NEGATIVE ones — proving
// that the matrix REFUSES to retry in cases where retry would
// amplify the bug:
//   - 4xx invalid request → fail_fast (no DoS-against-self)
//   - 401 → escalation (no brute-force against auth)
//   - 403 → escalation (no permission-shopping)
//   - guardrail block → HITL (no bypass attempt)
//   - data integrity violation → fail_fast (no corruption amplification)
//   - circuit_open_already → fail_fast (preserve downstream recovery)
//   - tool authorization denied → escalation (no scope-shopping)

import { describe, it, expect } from "vitest";
import {
  decisionFor,
  allDecisions,
  nextAction,
} from "./failure-decision-matrix";

describe("Iter 133 — failure decision matrix", () => {

  // ─── Catalog completeness ──────────────────────────────────

  it("BACKDOOR: 15 failure kinds covered across 4 categories", () => {
    const all = allDecisions();
    expect(all.length).toBe(15);
    const categories = new Set(all.map((d) => d.category));
    expect(categories.has("transient")).toBe(true);
    expect(categories.has("permanent")).toBe(true);
    expect(categories.has("safety")).toBe(true);
    expect(categories.has("quota")).toBe(true);
  });

  it("BACKDOOR: every decision carries rationale + STRIDE category + audit flag", () => {
    for (const d of allDecisions()) {
      expect(d.rationale.length).toBeGreaterThan(20);
      expect(d.strideCategory).toBeTruthy();
      expect(typeof d.recordToAudit).toBe("boolean");
      expect(typeof d.requiresHITL).toBe("boolean");
      expect(d.maxAttempts).toBeGreaterThanOrEqual(1);
    }
  });

  // ─── NEGATIVE: refusal-to-retry invariants ─────────────────

  it("NEGATIVE: 4xx invalid request → fail_fast, NOT retry (no self-DoS)", () => {
    const d = decisionFor("permanent_4xx_invalid_request");
    expect(d.primaryStrategy).toBe("fail_fast");
    expect(d.maxAttempts).toBe(1);  // no retry
  });

  it("NEGATIVE: 401 auth → escalation, NOT retry (no brute-force)", () => {
    const d = decisionFor("permanent_auth_401");
    expect(d.primaryStrategy).toBe("escalation");
    expect(d.maxAttempts).toBe(1);
    expect(d.strideCategory).toBe("S");  // Spoofing/Elevation
  });

  it("NEGATIVE: 403 auth → escalation, NOT retry (no permission-shopping)", () => {
    const d = decisionFor("permanent_auth_403");
    expect(d.primaryStrategy).toBe("escalation");
    expect(d.maxAttempts).toBe(1);
    expect(d.strideCategory).toBe("E");  // Elevation
  });

  it("NEGATIVE: guardrail block → HITL, NOT retry (no bypass)", () => {
    const d = decisionFor("guardrail_block");
    expect(d.primaryStrategy).toBe("hitl_review");
    expect(d.requiresHITL).toBe(true);
    expect(d.maxAttempts).toBe(1);
  });

  it("NEGATIVE: data integrity violation → fail_fast + HITL secondary (no amplification)", () => {
    const d = decisionFor("data_integrity_violation");
    expect(d.primaryStrategy).toBe("fail_fast");
    expect(d.secondaryStrategy).toBe("hitl_review");
    expect(d.requiresHITL).toBe(true);
    expect(d.maxAttempts).toBe(1);
  });

  it("NEGATIVE: circuit_open_already → fail_fast (preserve downstream recovery window)", () => {
    const d = decisionFor("circuit_open_already");
    expect(d.primaryStrategy).toBe("fail_fast");
  });

  it("NEGATIVE: tool authorization denied → escalation (no scope-shopping)", () => {
    const d = decisionFor("tool_authorization_denied");
    expect(d.primaryStrategy).toBe("escalation");
    expect(d.strideCategory).toBe("E");
  });

  // ─── Positive: retry-allowed cases ─────────────────────────

  it("BACKDOOR: network 5xx → retry with backoff, then circuit_breaker", () => {
    const d = decisionFor("transient_network_5xx");
    expect(d.primaryStrategy).toBe("retry");
    expect(d.secondaryStrategy).toBe("circuit_breaker");
    expect(d.maxAttempts).toBe(3);
    expect(d.initialBackoffMs).toBeGreaterThan(0);
  });

  it("BACKDOOR: rate limit 429 → retry with LONGER backoff (respect Retry-After)", () => {
    const d = decisionFor("transient_rate_limit_429");
    expect(d.primaryStrategy).toBe("retry");
    expect(d.initialBackoffMs).toBeGreaterThanOrEqual(2000);
    expect(d.recordToAudit).toBe(true);  // quota tracking
  });

  it("BACKDOOR: hallucination → fallback_model (try smarter model), then HITL", () => {
    const d = decisionFor("hallucination_detected");
    expect(d.primaryStrategy).toBe("fallback_model");
    expect(d.secondaryStrategy).toBe("hitl_review");
    expect(d.requiresHITL).toBe(true);
  });

  it("BACKDOOR: model quota → fallback_model, then escalation (budget review)", () => {
    const d = decisionFor("model_quota_exceeded");
    expect(d.primaryStrategy).toBe("fallback_model");
    expect(d.secondaryStrategy).toBe("escalation");
  });

  it("BACKDOOR: planner_invalid_plan → retry (replan once), HITL on 2nd failure", () => {
    const d = decisionFor("planner_invalid_plan");
    expect(d.primaryStrategy).toBe("retry");
    expect(d.maxAttempts).toBe(2);
    expect(d.secondaryStrategy).toBe("hitl_review");
  });

  // ─── nextAction() — per-attempt engine ─────────────────────

  it("BACKDOOR: nextAction returns primary strategy on attempt 1", () => {
    const action = nextAction({ failureKind: "transient_network_5xx", attemptNumber: 1 });
    expect(action.action).toBe("retry");
    expect(action.nextBackoffMs).toBe(500);  // 500 * 2^0
    expect(action.remainingAttempts).toBe(2);
  });

  it("BACKDOOR: nextAction returns exponential backoff on attempt 3", () => {
    const action = nextAction({ failureKind: "transient_network_5xx", attemptNumber: 3 });
    expect(action.action).toBe("retry");
    expect(action.nextBackoffMs).toBe(2000);  // 500 * 2^2
  });

  it("BACKDOOR: nextAction falls through to secondary when primary exhausted", () => {
    const action = nextAction({ failureKind: "transient_network_5xx", attemptNumber: 4 });
    expect(action.action).toBe("circuit_breaker");  // secondary
    expect(action.remainingAttempts).toBe(0);
  });

  it("NEGATIVE: nextAction on 4xx returns fail_fast even on attempt 1 (no retry)", () => {
    const action = nextAction({ failureKind: "permanent_4xx_invalid_request", attemptNumber: 1 });
    expect(action.action).toBe("fail_fast");
    expect(action.remainingAttempts).toBe(0);
  });

  // ─── Risk-level adjustment ─────────────────────────────────

  it("BACKDOOR: high-risk classification SHORTENS retry envelope by 1 (Art. 14 oversight)", () => {
    // Default 5xx network is 3 attempts; high-risk → 2.
    // After 2 attempts, falls through to secondary even though
    // minimal-risk would still have 1 attempt left.
    const action = nextAction({
      failureKind: "transient_network_5xx",
      attemptNumber: 3,
      riskLevel: "high_risk",
    });
    expect(action.action).toBe("circuit_breaker");  // secondary already
    expect(action.reason).toContain("exhausted");
  });

  it("BACKDOOR: minimal-risk preserves full retry envelope (cost discipline)", () => {
    const action = nextAction({
      failureKind: "transient_network_5xx",
      attemptNumber: 3,
      riskLevel: "minimal_risk",
    });
    expect(action.action).toBe("retry");  // still within envelope
    expect(action.remainingAttempts).toBe(0);  // last attempt
  });

  it("NEGATIVE: high-risk envelope minimum is 1 attempt (can't go to 0)", () => {
    // permanent_4xx already has maxAttempts=1; high-risk shouldn't
    // push it to 0.
    const action = nextAction({
      failureKind: "permanent_4xx_invalid_request",
      attemptNumber: 1,
      riskLevel: "high_risk",
    });
    expect(action.action).toBe("fail_fast");
  });

  it("NEGATIVE: nextAction with attemptNumber < 1 throws", () => {
    expect(() => nextAction({ failureKind: "transient_timeout", attemptNumber: 0 }))
      .toThrow(/attemptNumber must be >= 1/);
  });

  // ─── Compose with iters 130/131/132 ───────────────────────

  it("BACKDOOR: HITL-requiring decisions also recordToAudit=true (§38 compose)", () => {
    // The §38 audit row catches every HITL trigger so the
    // operator dashboard can correlate human-overrides to
    // failure kinds. Without this invariant, HITL events
    // would be invisible to the §53 maturity scorecard.
    for (const d of allDecisions()) {
      if (d.requiresHITL) {
        expect(d.recordToAudit).toBe(true);
      }
    }
  });

  it("BACKDOOR: every safety-category failure requires HITL (§48 + §132 compose)", () => {
    // Per iter 132 risk classification: high-risk safety failures
    // MUST escalate to a human. The matrix encodes this.
    const safety = allDecisions().filter((d) => d.category === "safety");
    expect(safety.length).toBeGreaterThan(0);
    expect(safety.every((d) => d.requiresHITL)).toBe(true);
  });
});
