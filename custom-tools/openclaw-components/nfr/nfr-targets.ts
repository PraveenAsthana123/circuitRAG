// Iter 130 (2026-05-20): NFR measurement methodology — closes the
// P0 GAPS row "§17 NFR Targets with no measurement methodology."
//
// Until this iter, GAPS.md listed targets like "99.9% availability,
// <5min recovery, Zero trust" without saying WHO measures, HOW,
// AT WHAT CADENCE, or what ALERT THRESHOLD triggers escalation.
// That's an aspirational SLO, not an operational NFR. This iter
// ships:
//
//   1. NFRDefinition type — every NFR carries the 4 measurement
//      protocol fields (how / by-whom / cadence / alert threshold)
//      so the spec is auditable + machine-checkable.
//
//   2. evaluateNFR(nfr, observed) → NFRMeasurement — a typed
//      evaluator that takes observed signals from iters 126-129
//      (daemon snapshot, rollback validator output, cycle log
//      window) and returns pass/fail + alert level per NFR.
//
//   3. CANONICAL_FLEET_NFRS — the 4 NFRs that bind the iter 126
//      daemon's operations to measurable thresholds:
//        - fleet-availability       (workingAgents ratio)
//        - rollback-time-app-layer  (estimatedAppRollbackSeconds)
//        - reconcile-latency-p95    (cycleDurationMs window)
//        - reconcile-cadence        (cycles per minute >= expected)
//
// Per CLAUDE.md §43 (drillable), §47.10 5-phase load testing (the
// NFRs ARE the load-test pass criteria), §53 enterprise maturity
// stack item 39 observability taxonomy + item 47 strategic alignment
// (NFRs bind ops to business commitments), §57.7 (every NFR target
// is now drillable, not aspirational).

import type { AgentFleetSnapshot } from "../10-agent-workflow/agent-fleet";

// ───────────────────────────── Types ─────────────────────────────

export type NFRSource =
  | "daemon_snapshot"
  | "rollback_validator"
  | "cycle_log_window";

/** What specific number to extract from the source. Decouples NFR
 *  identity (e.g., "fleet-availability-strict") from the measurement
 *  routine — a custom NFR with the same signal as a canonical one
 *  measures the same quantity but can carry different targets/thresholds. */
export type NFRSignal =
  | "availability"
  | "rollback_estimate_seconds"
  | "cycle_duration_p95_ms"
  | "cycles_per_minute";

export type NFRCadence =
  | "per_cycle"      // measure on each reconcile
  | "per_minute"
  | "per_hour"
  | "per_day"
  | "on_demand";     // measured ad-hoc (e.g., rollback estimate)

export type NFRComparison =
  | "gte"            // measured >= target  (e.g., availability)
  | "lte";           // measured <= target  (e.g., latency, recovery time)

export interface NFRDefinition {
  readonly id: string;
  readonly description: string;
  readonly target: number;
  readonly unit: string;
  readonly comparison: NFRComparison;
  readonly measureFrom: NFRSource;
  /** The specific quantity to extract from `measureFrom`. */
  readonly signal: NFRSignal;
  /** Looser than target — the 'still tolerable' line. When measured
   *  is on the WORSE side of this, page on-call (critical). When
   *  measured is between target and alertThreshold, emit warn. */
  readonly alertThreshold: number;
  /** Who is responsible for the SLA (e.g., "fleet-ops", "platform"). */
  readonly owner: string;
  readonly cadence: NFRCadence;
}

export type NFRAlertLevel = "ok" | "warn" | "critical" | "unknown";

export interface NFRMeasurement {
  readonly nfrId: string;
  readonly measuredValue: number | undefined;
  readonly target: number;
  readonly meetsTarget: boolean;
  readonly alertLevel: NFRAlertLevel;
  readonly reason?: string;
  readonly measuredAt: string;
}

export interface ObservedMetrics {
  readonly daemonSnapshot?: AgentFleetSnapshot;
  readonly estimatedRollbackSeconds?: number;
  /** Recent reconcile cycle durations (ms) — feeds p95 / cadence NFRs. */
  readonly cycleDurationsMs?: ReadonlyArray<number>;
  /** Number of cycles observed in the most recent 60s window. */
  readonly cyclesPerMinute?: number;
}

// ───────────────────────────── Canonical NFRs ────────────────────

// Note on alertThreshold direction:
//   For comparison="gte" (higher is better), alertThreshold is LOWER
//     than target — measured below alertThreshold = critical.
//   For comparison="lte" (lower is better), alertThreshold is HIGHER
//     than target — measured above alertThreshold = critical.
//   The "warn" band lies between target and alertThreshold.

export const CANONICAL_FLEET_NFRS: ReadonlyArray<NFRDefinition> = [
  {
    id: "fleet-availability",
    description: "Fraction of desired agents currently working (workingAgents / desiredActiveAgents)",
    target: 0.99,
    unit: "ratio",
    comparison: "gte",
    measureFrom: "daemon_snapshot",
    signal: "availability",
    alertThreshold: 0.95,  // looser than target — page when availability drops below 95%
    owner: "fleet-ops",
    cadence: "per_cycle",
  },
  {
    id: "rollback-time-app-layer",
    description: "Estimated wall-clock for App-layer kubectl rollback (no DB/AI/Infra rollback)",
    target: 300,  // 5 minutes per the original GAPS aspiration
    unit: "seconds",
    comparison: "lte",
    measureFrom: "rollback_validator",
    signal: "rollback_estimate_seconds",
    alertThreshold: 420,  // looser than target — page if estimate > 7 min
    owner: "platform",
    cadence: "on_demand",
  },
  {
    id: "reconcile-latency-p95",
    description: "p95 of reconcile cycle duration across recent window",
    target: 1000,
    unit: "milliseconds",
    comparison: "lte",
    measureFrom: "cycle_log_window",
    signal: "cycle_duration_p95_ms",
    alertThreshold: 2000,  // looser than target — page if p95 > 2s
    owner: "fleet-ops",
    cadence: "per_minute",
  },
  {
    id: "reconcile-cadence",
    description: "Reconcile cycles observed in the last 60s window (proves daemon is alive + cycling)",
    target: 2,   // assuming 30s interval, expect 2/min
    unit: "cycles_per_minute",
    comparison: "gte",
    measureFrom: "cycle_log_window",
    signal: "cycles_per_minute",
    alertThreshold: 1,  // looser than target — page if cadence drops to 1/min
    owner: "fleet-ops",
    cadence: "per_minute",
  },
];

// ───────────────────────────── Evaluator ─────────────────────────

export function evaluateNFR(nfr: NFRDefinition, observed: ObservedMetrics): NFRMeasurement {
  const measuredAt = new Date().toISOString();
  const measuredValue = extractMeasured(nfr, observed);

  if (measuredValue === undefined) {
    return {
      nfrId: nfr.id,
      measuredValue: undefined,
      target: nfr.target,
      meetsTarget: false,
      alertLevel: "unknown",
      reason: `No observation available for source ${nfr.measureFrom}`,
      measuredAt,
    };
  }

  const meetsTarget = nfr.comparison === "gte"
    ? measuredValue >= nfr.target
    : measuredValue <= nfr.target;

  // alertThreshold is LOOSER than target (the still-tolerable line).
  // For gte: alertThreshold < target, measured BELOW alertThreshold = critical.
  // For lte: alertThreshold > target, measured ABOVE alertThreshold = critical.
  const crossedAlertLine = nfr.comparison === "gte"
    ? measuredValue < nfr.alertThreshold
    : measuredValue > nfr.alertThreshold;

  const alertLevel: NFRAlertLevel =
    meetsTarget       ? "ok"        // measured beats target
    : crossedAlertLine ? "critical" // measured crossed the page-on-call line
    : "warn";                       // measured missed target but didn't cross alert

  return {
    nfrId: nfr.id,
    measuredValue,
    target: nfr.target,
    meetsTarget,
    alertLevel,
    reason: meetsTarget
      ? undefined
      : `measured ${measuredValue} ${nfr.comparison === "gte" ? "<" : ">"} target ${nfr.target} ${nfr.unit}`,
    measuredAt,
  };
}

export function evaluateAllNFRs(
  nfrs: ReadonlyArray<NFRDefinition>,
  observed: ObservedMetrics,
): ReadonlyArray<NFRMeasurement> {
  return nfrs.map((nfr) => evaluateNFR(nfr, observed));
}

// ───────────────────────────── Helpers ────────────────────────────

function extractMeasured(nfr: NFRDefinition, observed: ObservedMetrics): number | undefined {
  // Switch on signal (not nfr.id) so a custom NFR with the same
  // signal as a canonical NFR but a different id/threshold reuses
  // the same measurement routine.
  switch (nfr.signal) {
    case "availability": {
      const s = observed.daemonSnapshot;
      if (!s) return undefined;
      return s.desiredActiveAgents > 0 ? s.workingAgents / s.desiredActiveAgents : 0;
    }
    case "rollback_estimate_seconds":
      return observed.estimatedRollbackSeconds;
    case "cycle_duration_p95_ms":
      return p95(observed.cycleDurationsMs);
    case "cycles_per_minute":
      return observed.cyclesPerMinute;
    default:
      return undefined;
  }
}

function p95(values: ReadonlyArray<number> | undefined): number | undefined {
  if (!values || values.length === 0) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  // For a small window (< 20 samples), p95 of n samples = sorted[ceil(0.95*n) - 1]
  const idx = Math.max(0, Math.ceil(sorted.length * 0.95) - 1);
  return sorted[idx];
}
