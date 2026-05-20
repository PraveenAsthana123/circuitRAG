// Iter 134 (2026-05-20): drill the auto-heal catalog. The MOST
// IMPORTANT invariants are:
//   1. Every iter 133 FailureKind lands in exactly ONE bucket
//      (auto_healable / escalation_required / hitl_required) —
//      no kind is missed, no kind is double-bucketed.
//   2. guardrail_block / 401 / 403 / data_integrity / hallucination
//      are NEVER in auto_healable (the cardinal §57.7 rules from
//      iter 133 re-asserted at the catalog layer).

import { describe, it, expect } from "vitest";
import {
  bucketFor,
  isAutoHealable,
  autoHealCatalog,
  escalationCatalog,
  hitlCatalog,
  escalationTargetFor,
} from "./auto-heal-catalog";
import { allDecisions, FailureKind } from "./failure-decision-matrix";

describe("Iter 134 — auto-heal catalog", () => {

  // ─── Partition completeness (the most important drill) ─────

  it("BACKDOOR: every FailureKind from iter 133 lands in exactly one bucket", () => {
    // Sum the three catalogs; assert no overlap + no omission.
    const auto = new Set(autoHealCatalog().map((e) => e.failureKind));
    const esc = new Set(escalationCatalog().map((e) => e.failureKind));
    const hitl = new Set(hitlCatalog().map((e) => e.failureKind));

    // No overlap pairwise
    for (const k of auto) expect(esc.has(k)).toBe(false);
    for (const k of auto) expect(hitl.has(k)).toBe(false);
    for (const k of esc) expect(hitl.has(k)).toBe(false);

    // Union equals all known FailureKinds
    const all = new Set(allDecisions().map((d) => d.failureKind));
    expect(auto.size + esc.size + hitl.size).toBe(all.size);
    for (const k of all) {
      expect(auto.has(k) || esc.has(k) || hitl.has(k)).toBe(true);
    }
  });

  it("BACKDOOR: bucketFor returns exactly the bucket the kind appears in", () => {
    for (const e of autoHealCatalog()) expect(bucketFor(e.failureKind)).toBe("auto_healable");
    for (const e of escalationCatalog()) expect(bucketFor(e.failureKind)).toBe("escalation_required");
    for (const e of hitlCatalog()) expect(bucketFor(e.failureKind)).toBe("hitl_required");
  });

  // ─── Cardinal NEGATIVES: things that MUST NOT auto-heal ────

  it("NEGATIVE §57.7: guardrail_block is NOT auto-healable (no bypass attempt)", () => {
    expect(isAutoHealable("guardrail_block")).toBe(false);
    expect(bucketFor("guardrail_block")).toBe("hitl_required");
  });

  it("NEGATIVE §57.7: permanent_auth_401 is NOT auto-healable (no brute-force)", () => {
    expect(isAutoHealable("permanent_auth_401")).toBe(false);
    expect(bucketFor("permanent_auth_401")).toBe("escalation_required");
  });

  it("NEGATIVE §57.7: permanent_auth_403 is NOT auto-healable (no permission-shopping)", () => {
    expect(isAutoHealable("permanent_auth_403")).toBe(false);
    expect(bucketFor("permanent_auth_403")).toBe("escalation_required");
  });

  it("NEGATIVE §57.7: data_integrity_violation is NOT auto-healable (no corruption amplification)", () => {
    expect(isAutoHealable("data_integrity_violation")).toBe(false);
    expect(bucketFor("data_integrity_violation")).toBe("hitl_required");
  });

  it("NEGATIVE §57.7: hallucination_detected is NOT auto-healable (regulatory §48.5)", () => {
    // Even though the primary strategy is fallback_model (which is
    // auto-heal-flavored), the requiresHITL flag from iter 133
    // gates this into the HITL bucket. The §48.5 four-part
    // contract demands human review of citation violations.
    expect(isAutoHealable("hallucination_detected")).toBe(false);
    expect(bucketFor("hallucination_detected")).toBe("hitl_required");
  });

  it("NEGATIVE §57.7: permanent_4xx is NOT auto-healable (caller bug, not system)", () => {
    expect(isAutoHealable("permanent_4xx_invalid_request")).toBe(false);
    expect(bucketFor("permanent_4xx_invalid_request")).toBe("escalation_required");
  });

  it("NEGATIVE §57.7: tool_authorization_denied is NOT auto-healable", () => {
    expect(isAutoHealable("tool_authorization_denied")).toBe(false);
    expect(bucketFor("tool_authorization_denied")).toBe("escalation_required");
  });

  // ─── POSITIVE: things that SHOULD auto-heal ────────────────

  it("BACKDOOR: transient_network_5xx is auto-healable (retry strategy)", () => {
    expect(isAutoHealable("transient_network_5xx")).toBe(true);
    const entry = autoHealCatalog().find((e) => e.failureKind === "transient_network_5xx");
    expect(entry).toBeDefined();
    expect(entry!.healingStrategy).toBe("retry");
    expect(entry!.maxAttempts).toBe(3);
  });

  it("BACKDOOR: transient_rate_limit_429 is auto-healable", () => {
    expect(isAutoHealable("transient_rate_limit_429")).toBe(true);
  });

  it("BACKDOOR: circuit_open_already is auto-healable (primary=fail_fast preserves recovery window; secondary=fallback_model is the effective heal)", () => {
    expect(isAutoHealable("circuit_open_already")).toBe(true);
    const entry = autoHealCatalog().find((e) => e.failureKind === "circuit_open_already");
    expect(entry).toBeDefined();
    // The effective heal is the SECONDARY (fallback_model) — primary
    // fail_fast preserves the downstream's recovery window per §47.8,
    // and the catalog exposes the effective recovery path.
    expect(entry!.healingStrategy).toBe("fallback_model");
  });

  it("BACKDOOR: model_quota_exceeded is auto-healable via fallback_model primary", () => {
    expect(isAutoHealable("model_quota_exceeded")).toBe(true);
    const entry = autoHealCatalog().find((e) => e.failureKind === "model_quota_exceeded");
    expect(entry!.healingStrategy).toBe("fallback_model");
  });

  // ─── Catalog metadata ──────────────────────────────────────

  it("BACKDOOR: every auto-heal entry carries estimatedRecoverySeconds (DR metrics input)", () => {
    for (const e of autoHealCatalog()) {
      expect(e.estimatedRecoverySeconds).toBeGreaterThanOrEqual(0);
      expect(e.maxAttempts).toBeGreaterThanOrEqual(1);
    }
  });

  it("BACKDOOR: estimatedRecoverySeconds reflects exponential backoff (3 attempts × 500ms backoff > 3 attempts × 0)", () => {
    const networkEntry = autoHealCatalog().find((e) => e.failureKind === "transient_network_5xx")!;
    const timeoutEntry = autoHealCatalog().find((e) => e.failureKind === "transient_timeout")!;
    // network_5xx: 3 attempts with 500ms backoff = ~600+1000+2000+200*3 = 4200ms ≈ 5s
    // timeout: 1 attempt with 0 backoff = ~200ms = 1s ceil
    expect(networkEntry.estimatedRecoverySeconds).toBeGreaterThan(timeoutEntry.estimatedRecoverySeconds);
  });

  it("BACKDOOR: escalationCatalog entries carry named target + reason (operator runbook input)", () => {
    for (const e of escalationCatalog()) {
      expect(e.escalationTarget).toBeTruthy();
      expect(e.reason.length).toBeGreaterThan(20);
    }
  });

  it("BACKDOOR: hitlCatalog entries carry named review queue (composes with iter 119 HumanReviewQueue)", () => {
    for (const e of hitlCatalog()) {
      expect(e.reviewQueue).toBeTruthy();
      expect(e.reason.length).toBeGreaterThan(20);
    }
  });

  // ─── escalationTargetFor() helper ──────────────────────────

  it("BACKDOOR: escalationTargetFor returns the named team for escalation-bucket kinds", () => {
    expect(escalationTargetFor("permanent_auth_401")).toBe("auth-ops");
    expect(escalationTargetFor("permanent_4xx_invalid_request")).toBe("caller-team");
    expect(escalationTargetFor("tool_authorization_denied")).toBe("platform");
  });

  it("NEGATIVE: escalationTargetFor returns undefined for model_quota_exceeded (now auto-healable via fallback)", () => {
    // model_quota_exceeded has primary=fallback_model (auto-heal),
    // secondary=escalation (escape hatch). The PRIMARY drives the
    // bucket — the system DOES try to heal first.
    expect(escalationTargetFor("model_quota_exceeded")).toBeUndefined();
  });

  it("NEGATIVE: escalationTargetFor returns undefined for auto-healable kinds", () => {
    expect(escalationTargetFor("transient_network_5xx")).toBeUndefined();
  });

  it("NEGATIVE: escalationTargetFor returns undefined for HITL kinds", () => {
    expect(escalationTargetFor("guardrail_block")).toBeUndefined();
  });

  // ─── §59.1 MDD: catalog is DERIVED, not hand-maintained ────

  it("BACKDOOR: adding a new FailureKind to iter 133 matrix would automatically place it in a catalog", () => {
    // This drill asserts the DERIVATION pattern — the catalog
    // size + total kinds count match by definition because
    // bucketFor() partitions allDecisions(). A future iter
    // adding a new failure kind to iter 133 will see it
    // automatically appear in one of the three catalogs, with
    // no hand-edit to this file required.
    const totalKinds = allDecisions().length;
    const partitioned = autoHealCatalog().length + escalationCatalog().length + hitlCatalog().length;
    expect(partitioned).toBe(totalKinds);
  });
});
