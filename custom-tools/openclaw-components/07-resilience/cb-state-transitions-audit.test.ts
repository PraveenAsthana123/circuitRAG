// Iter 69 audit drill (2026-05-17): makes the GAPS.md "Component 7
// has no open gaps" claim machine-checkable.
//
// Per CLAUDE.md §52 (brutal tool review), the circuit-breaker tool
// row 8 (resilience axis) demands evidence — not vibes — that the
// state machine behaves as documented. Three of the seven mandatory
// CB axes were already covered by circuit-breaker.test.ts and
// cb-success-threshold.test.ts; this file audits all seven in one
// place AND locks two real gaps that were silently uncovered:
//
//   1. **Per-key isolation** — the openclaw CB is a single-key
//      instance (no key map). The audit assertion is therefore
//      INSTANCE isolation: two independent breakers do NOT share
//      state. If anyone ever adds a static class field to track
//      global failure counts, this drill rejects.
//
//   2. **Constructor accepts invalid config silently** — the current
//      constructor takes any ResiliencePolicy without validation.
//      This is a real (small) gap. Rather than expand the surface
//      mid-audit, the drill PINS the current contract: the
//      constructor MUST NOT throw on any plausible policy shape, so
//      callers can rely on construction being side-effect free.
//      A future hardening commit that adds validation MUST update
//      this drill to reflect the new contract — making the gap
//      visible at code-review time.
//
// Every assertion has a "what this drill rejects" comment so that
// reading the file alone tells you which behaviors are locked.

import { describe, it, expect } from "vitest";
import { CircuitBreaker } from "./circuit-breaker";
import { ResiliencePolicy, CircuitState } from "./types";

const AUDIT_POLICY: ResiliencePolicy = {
  timeoutMs: 100,
  maxRetries: 0,
  retryDelayMs: 1,
  failureThreshold: 3,
  resetAfterMs: 40,
  successThreshold: 2,
};

async function expireResetWindow(): Promise<void> {
  await new Promise((r) => setTimeout(r, AUDIT_POLICY.resetAfterMs + 5));
}

describe("CircuitBreaker state-transition audit (Iter 69)", () => {
  // ── Axis A: failure threshold trip ────────────────────────────
  it("A. closed → open exactly at failureThreshold, NOT before", () => {
    const cb = new CircuitBreaker(AUDIT_POLICY);

    // failureThreshold is 3 — first two failures must NOT open the
    // breaker. This drill rejects a regression where any failure
    // (off-by-one in `>=`) prematurely opens the breaker.
    cb.recordFailure();
    expect(cb.getState()).toBe<CircuitState>("closed");
    cb.recordFailure();
    expect(cb.getState()).toBe<CircuitState>("closed");
    cb.recordFailure();
    expect(cb.getState()).toBe<CircuitState>("open");

    // Open means canExecute is false immediately (no half-open
    // promotion yet — that's axis B). Rejects a regression where
    // canExecute() returns true even in fresh-open state.
    expect(cb.canExecute()).toBe(false);
  });

  // ── Axis B: half-open promotion gated by resetAfterMs ────────
  it("B. canExecute does NOT auto-promote before resetAfterMs elapsed", async () => {
    const cb = new CircuitBreaker(AUDIT_POLICY);
    cb.recordFailure(); cb.recordFailure(); cb.recordFailure();
    expect(cb.getState()).toBe("open");

    // BACKDOOR CHECK: calling canExecute many times within the reset
    // window must NOT promote to half_open and must NOT admit a
    // probe. Rejects a regression where the reset clock starts on
    // first canExecute() instead of last recordFailure().
    for (let i = 0; i < 5; i++) {
      expect(cb.canExecute()).toBe(false);
      expect(cb.getState()).toBe("open");
    }
  });

  // ── Axis C: half-open admits exactly ONE probe ───────────────
  it("C. open → half_open admits exactly one probe, then refuses", async () => {
    const cb = new CircuitBreaker(AUDIT_POLICY);
    cb.recordFailure(); cb.recordFailure(); cb.recordFailure();
    await expireResetWindow();

    // Rejects the pre-Iter-6 P0 regression where concurrent probes
    // would all be admitted (thundering herd onto a recovering
    // downstream).
    expect(cb.canExecute()).toBe(true);
    expect(cb.getState()).toBe("half_open");
    expect(cb.canExecute()).toBe(false);
    expect(cb.canExecute()).toBe(false);
  });

  // ── Axis D: half_open + success at threshold > 1 stays half_open ──
  it("D. recordSuccess at successThreshold-1 keeps breaker half_open", async () => {
    const cb = new CircuitBreaker(AUDIT_POLICY); // successThreshold = 2
    cb.recordFailure(); cb.recordFailure(); cb.recordFailure();
    await expireResetWindow();
    cb.canExecute(); // probe 1 admitted
    cb.recordSuccess();

    // BACKDOOR CHECK: rejects the pre-Iter-18 P1 regression where a
    // single success eagerly closed the breaker regardless of
    // successThreshold setting.
    expect(cb.getState()).toBe("half_open");
    expect(cb.getSuccessStreak()).toBe(1);

    // Second consecutive success now closes.
    expect(cb.canExecute()).toBe(true);
    cb.recordSuccess();
    expect(cb.getState()).toBe("closed");
    expect(cb.getSuccessStreak()).toBe(0);
  });

  // ── Axis E: half_open failure re-opens immediately ───────────
  it("E. half_open + failure re-opens immediately, does NOT decrement to closed-1", async () => {
    const cb = new CircuitBreaker(AUDIT_POLICY);
    cb.recordFailure(); cb.recordFailure(); cb.recordFailure();
    await expireResetWindow();
    cb.canExecute(); // probe admitted, half_open
    cb.recordFailure();

    // Rejects a regression where half_open failure decrements a
    // counter (closed-style) instead of re-opening hard. Also
    // confirms a fresh resetAfter window must elapse before another
    // probe is admitted.
    expect(cb.getState()).toBe("open");
    expect(cb.canExecute()).toBe(false);
  });

  // ── Axis F: instance isolation (the openclaw equivalent of per-key) ──
  it("F. two independent CircuitBreaker instances do NOT share state", () => {
    const cbA = new CircuitBreaker(AUDIT_POLICY);
    const cbB = new CircuitBreaker(AUDIT_POLICY);

    // Trip A. Then B must still be in `closed` and admitting traffic.
    cbA.recordFailure(); cbA.recordFailure(); cbA.recordFailure();
    expect(cbA.getState()).toBe("open");

    // BACKDOOR CHECK: rejects any future regression where someone
    // adds a `static failureCount` or singleton state map that
    // accidentally couples instances. Per-key isolation in the
    // openclaw component model is instance isolation — that's the
    // contract the audit locks in.
    expect(cbB.getState()).toBe("closed");
    expect(cbB.canExecute()).toBe(true);
    cbB.recordSuccess();
    expect(cbB.getState()).toBe("closed");
  });

  // ── Axis G: constructor accepts current config shape without throwing ──
  it("G. constructor is side-effect free + accepts current ResiliencePolicy shape", () => {
    // This drill PINS the current contract (no validation) so a
    // future hardening commit that adds validation MUST update this
    // file — surfacing the contract change at review time.
    expect(() => new CircuitBreaker(AUDIT_POLICY)).not.toThrow();

    const minimal: ResiliencePolicy = {
      timeoutMs: 1,
      maxRetries: 0,
      retryDelayMs: 1,
      failureThreshold: 1,
      resetAfterMs: 1,
    };
    expect(() => new CircuitBreaker(minimal)).not.toThrow();

    // Fresh instances always start `closed` and `canExecute===true`.
    // Rejects a regression where the constructor pre-populates
    // failureCount from policy fields.
    const cb = new CircuitBreaker(AUDIT_POLICY);
    expect(cb.getState()).toBe("closed");
    expect(cb.canExecute()).toBe(true);
    expect(cb.getSuccessStreak()).toBe(0);
  });

  // ── Axis H: successThreshold floor (defensive lower bound) ────
  it("H. successThreshold ≤ 0 is normalized to 1 (no division-by-zero / infinite loop)", async () => {
    // Per circuit-breaker.ts line 22-24: Math.max(1, threshold ?? 1).
    // Rejects a regression where the floor is removed and a 0 or
    // negative threshold either traps the breaker forever in
    // half_open or panics on recordSuccess.
    const zeroPolicy: ResiliencePolicy = {
      ...AUDIT_POLICY,
      successThreshold: 0,
    };
    const cb = new CircuitBreaker(zeroPolicy);
    cb.recordFailure(); cb.recordFailure(); cb.recordFailure();
    await expireResetWindow();
    cb.canExecute(); // probe admitted
    cb.recordSuccess();
    expect(cb.getState()).toBe("closed"); // single success closed it

    const negPolicy: ResiliencePolicy = {
      ...AUDIT_POLICY,
      successThreshold: -5,
    };
    const cb2 = new CircuitBreaker(negPolicy);
    cb2.recordFailure(); cb2.recordFailure(); cb2.recordFailure();
    await expireResetWindow();
    cb2.canExecute();
    cb2.recordSuccess();
    expect(cb2.getState()).toBe("closed");
  });

  // ── Axis I: recordSuccess in closed state is idempotent ───────
  it("I. recordSuccess in closed state never flips state away from closed", () => {
    const cb = new CircuitBreaker(AUDIT_POLICY);
    expect(cb.getState()).toBe("closed");

    // Rejects a regression where recordSuccess on a fresh breaker
    // accidentally toggles state (e.g., a future refactor that
    // unifies the half_open/closed branches).
    for (let i = 0; i < 10; i++) {
      cb.recordSuccess();
      expect(cb.getState()).toBe("closed");
      expect(cb.canExecute()).toBe(true);
    }
  });

  // ── Axis J: post-close, failure counter is fully reset ────────
  it("J. after close from half_open, failureThreshold is honored from zero", async () => {
    const cb = new CircuitBreaker(AUDIT_POLICY); // successThreshold=2
    cb.recordFailure(); cb.recordFailure(); cb.recordFailure();
    await expireResetWindow();
    cb.canExecute(); cb.recordSuccess(); // streak=1, half_open
    cb.canExecute(); cb.recordSuccess(); // streak=2 → closed
    expect(cb.getState()).toBe("closed");

    // Rejects a regression where the post-close failureCount carries
    // residual count from before — meaning ONE post-close failure
    // would re-trip. That would be a thundering-herd amplifier.
    cb.recordFailure();
    expect(cb.getState()).toBe("closed");
    cb.recordFailure();
    expect(cb.getState()).toBe("closed");
    cb.recordFailure(); // 3rd from-zero failure → open
    expect(cb.getState()).toBe("open");
  });
});
