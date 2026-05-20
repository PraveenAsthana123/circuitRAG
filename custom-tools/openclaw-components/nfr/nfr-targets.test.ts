// Iter 130 (2026-05-20): drills the NFR evaluator + canonical NFR
// catalog. Locks the §17 measurement-methodology invariants:
// every NFR has measurement source + cadence + owner + alert
// threshold + comparison direction. Without these fields the NFR
// is aspirational, not operational.
//
// Negative assertions (≥ 3 per §43):
//   - Missing observation source → alertLevel "unknown" (NOT crash)
//   - Degraded fleet (60/100 working) → critical alert on availability
//   - Latency above target → critical
//   - Latency between target and alertThreshold → warn (3-state alarming)
//   - 0 cycles per minute (daemon stuck) → critical on cadence
//   - p95 with empty window → unknown, not 0 (defensive)

import { describe, it, expect } from "vitest";
import {
  CANONICAL_FLEET_NFRS,
  evaluateNFR,
  evaluateAllNFRs,
  NFRDefinition,
} from "./nfr-targets";
import type { AgentFleetSnapshot } from "../10-agent-workflow/agent-fleet";

const HEALTHY: AgentFleetSnapshot = {
  desiredActiveAgents: 100,
  totalAgents: 100,
  activeAgents: 100,
  readyAgents: 100,
  workingAgents: 100,
  notWorkingAgents: 0,
  allAgentsWorking: true,
  warmingAgents: 0,
  degradedAgents: 0,
  stoppedAgents: 0,
};

const AVAIL_NFR = CANONICAL_FLEET_NFRS.find((n) => n.id === "fleet-availability")!;
const ROLLBACK_NFR = CANONICAL_FLEET_NFRS.find((n) => n.id === "rollback-time-app-layer")!;
const LATENCY_NFR = CANONICAL_FLEET_NFRS.find((n) => n.id === "reconcile-latency-p95")!;
const CADENCE_NFR = CANONICAL_FLEET_NFRS.find((n) => n.id === "reconcile-cadence")!;

describe("Iter 130 — NFR measurement methodology", () => {

  // ─── Canonical catalog completeness ────────────────────────

  it("BACKDOOR: CANONICAL_FLEET_NFRS exposes 4 named NFRs", () => {
    const ids = CANONICAL_FLEET_NFRS.map((n) => n.id).sort();
    expect(ids).toEqual([
      "fleet-availability",
      "reconcile-cadence",
      "reconcile-latency-p95",
      "rollback-time-app-layer",
    ]);
  });

  it("BACKDOOR §17: every NFR carries measurement-protocol fields (owner/cadence/source/threshold)", () => {
    for (const nfr of CANONICAL_FLEET_NFRS) {
      expect(nfr.owner).toBeTruthy();
      expect(nfr.cadence).toBeTruthy();
      expect(nfr.measureFrom).toBeTruthy();
      expect(typeof nfr.alertThreshold).toBe("number");
      expect(typeof nfr.target).toBe("number");
      expect(nfr.unit).toBeTruthy();
      expect(nfr.description).toBeTruthy();
    }
  });

  // ─── Availability NFR ──────────────────────────────────────

  it("BACKDOOR: 100/100 working → availability NFR passes with alertLevel ok", () => {
    const result = evaluateNFR(AVAIL_NFR, { daemonSnapshot: HEALTHY });
    expect(result.measuredValue).toBe(1.0);
    expect(result.meetsTarget).toBe(true);
    expect(result.alertLevel).toBe("ok");
  });

  it("NEGATIVE: 60/100 working (degraded) → availability NFR fails with critical alert", () => {
    const degraded: AgentFleetSnapshot = { ...HEALTHY, workingAgents: 60, notWorkingAgents: 40, allAgentsWorking: false };
    const result = evaluateNFR(AVAIL_NFR, { daemonSnapshot: degraded });
    expect(result.measuredValue).toBe(0.6);
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("critical");
    expect(result.reason).toContain("0.6");
  });

  it("NEGATIVE: 97/100 working → meetsTarget=false but only WARN (between target 0.99 and alert 0.95)", () => {
    // 3-state alarming: this is the warn band. NFR target missed
    // but not yet at page-on-call threshold.
    const slightlyDegraded: AgentFleetSnapshot = { ...HEALTHY, workingAgents: 97, notWorkingAgents: 3 };
    const result = evaluateNFR(AVAIL_NFR, { daemonSnapshot: slightlyDegraded });
    expect(result.measuredValue).toBe(0.97);
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("warn");  // 0.97 >= 0.95 alert threshold but < 0.99 target
  });

  // ─── Rollback-time NFR ─────────────────────────────────────

  it("BACKDOOR: rollback estimate 210s → meets target 300s, ok", () => {
    const result = evaluateNFR(ROLLBACK_NFR, { estimatedRollbackSeconds: 210 });
    expect(result.meetsTarget).toBe(true);
    expect(result.alertLevel).toBe("ok");
  });

  it("NEGATIVE: rollback estimate 360s → fails 300s target but WARN (still under 420s alert)", () => {
    // 3-state alarming: missed target but didn't cross page-on-call line.
    const result = evaluateNFR(ROLLBACK_NFR, { estimatedRollbackSeconds: 360 });
    expect(result.meetsTarget).toBe(false);  // 360 > 300
    expect(result.alertLevel).toBe("warn");  // 360 <= 420 alert threshold
  });

  it("NEGATIVE: rollback estimate 600s → fails target AND crosses alert → CRITICAL", () => {
    const result = evaluateNFR(ROLLBACK_NFR, { estimatedRollbackSeconds: 600 });
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("critical");  // 600 > 420 alert
  });

  // ─── Latency NFR ───────────────────────────────────────────

  it("BACKDOOR: cycle durations 100ms p95 → meets 1000ms target", () => {
    const cycleDurationsMs = [50, 80, 100, 120, 150];
    const result = evaluateNFR(LATENCY_NFR, { cycleDurationsMs });
    expect(result.meetsTarget).toBe(true);
    expect(result.alertLevel).toBe("ok");
  });

  it("NEGATIVE: cycle duration spike 1500ms p95 → fails 1000ms target but WARN (under 2000ms alert)", () => {
    const cycleDurationsMs = [100, 200, 300, 800, 1500];
    const result = evaluateNFR(LATENCY_NFR, { cycleDurationsMs });
    expect(result.measuredValue).toBe(1500);
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("warn");  // 1500 between 1000 target and 2000 alert
  });

  it("NEGATIVE: cycle duration 2500ms p95 → fails target AND crosses alert → CRITICAL", () => {
    const cycleDurationsMs = [100, 200, 300, 1800, 2500];
    const result = evaluateNFR(LATENCY_NFR, { cycleDurationsMs });
    expect(result.measuredValue).toBe(2500);
    expect(result.alertLevel).toBe("critical");  // 2500 > 2000 alert
  });

  it("NEGATIVE: empty cycle window → measured=undefined, alertLevel=unknown (defensive)", () => {
    const result = evaluateNFR(LATENCY_NFR, { cycleDurationsMs: [] });
    expect(result.measuredValue).toBeUndefined();
    expect(result.alertLevel).toBe("unknown");
    expect(result.reason).toContain("No observation");
  });

  // ─── Cadence NFR ───────────────────────────────────────────

  it("BACKDOOR: 4 cycles/min → meets target 2", () => {
    const result = evaluateNFR(CADENCE_NFR, { cyclesPerMinute: 4 });
    expect(result.meetsTarget).toBe(true);
    expect(result.alertLevel).toBe("ok");
  });

  it("NEGATIVE: 0 cycles/min (daemon stuck) → critical on cadence", () => {
    const result = evaluateNFR(CADENCE_NFR, { cyclesPerMinute: 0 });
    expect(result.measuredValue).toBe(0);
    expect(result.meetsTarget).toBe(false);
    expect(result.alertLevel).toBe("critical");
  });

  // ─── Missing observation handling ──────────────────────────

  it("NEGATIVE: NFR with no observed source → alertLevel unknown (NOT crash)", () => {
    const result = evaluateNFR(AVAIL_NFR, {});
    expect(result.measuredValue).toBeUndefined();
    expect(result.alertLevel).toBe("unknown");
    expect(result.meetsTarget).toBe(false);
  });

  // ─── Batch evaluator ───────────────────────────────────────

  it("BACKDOOR: evaluateAllNFRs returns 1 measurement per NFR", () => {
    const results = evaluateAllNFRs(CANONICAL_FLEET_NFRS, {
      daemonSnapshot: HEALTHY,
      estimatedRollbackSeconds: 210,
      cycleDurationsMs: [100, 200],
      cyclesPerMinute: 4,
    });
    expect(results.length).toBe(CANONICAL_FLEET_NFRS.length);
    expect(results.every((r) => r.alertLevel === "ok")).toBe(true);
  });

  it("BACKDOOR: each NFR measurement carries measuredAt timestamp + target field", () => {
    const result = evaluateNFR(AVAIL_NFR, { daemonSnapshot: HEALTHY });
    expect(result.measuredAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(result.target).toBe(AVAIL_NFR.target);
    expect(result.nfrId).toBe(AVAIL_NFR.id);
  });

  // ─── Custom NFR injection ──────────────────────────────────

  it("BACKDOOR: custom NFR reusing canonical 'availability' signal with stricter target", () => {
    // Operator wires a tier-1-tenant SLO that's stricter than
    // the default fleet-wide NFR. The 'signal' field decouples
    // measurement from id/threshold so a custom NFR inherits
    // the availability computation without copy-paste.
    const strictAvail: NFRDefinition = {
      ...AVAIL_NFR,
      id: "fleet-availability-tier1-tenant",
      target: 0.995,        // stricter target
      alertThreshold: 0.99, // still LOOSER than target (canonical 3-band)
    };
    const result = evaluateNFR(strictAvail, { daemonSnapshot: { ...HEALTHY, workingAgents: 99, notWorkingAgents: 1 } });
    expect(result.measuredValue).toBe(0.99);
    expect(result.meetsTarget).toBe(false);  // 0.99 < 0.995 strict target
    expect(result.alertLevel).toBe("warn");  // 0.99 == alertThreshold — not crossed, so warn not critical
  });
});
